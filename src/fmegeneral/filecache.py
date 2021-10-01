"""FME file caching mechanism: PR73324."""

from __future__ import absolute_import, division, print_function
import logging
import os
import shutil
import subprocess
import tempfile

import sys
from sqlite3 import DatabaseError

from diskcache import Cache
from fmegeneral.fmeutil import stringArrayToDict

FME_WEB_FILE_CACHE_SIZE_PROPERTY_CATEGORY = 'web_file_cache_size'
FME_WEB_FILE_CACHE_SIZE_KEY = 'web-file-cache-size'


def get_cache(cache_name='FMEFILECACHE',
              cache_root_path=None,
              logger=None,
              **kwargs):
    """Get a configured FMEFileCache instance.

    :param str cache_name: Name of the cache. Defaults to a global cache intended to be shared across all of FME.
    :param str cache_root_path: Parent directory of the cache.
       Default is :func:`tempfile.gettempdir` (which may be previously configured to be to `FME_TEMP`),
       in a subdirectory called `FMEFILECACHE`.
    :param Logger logger: Emit debug messages to this log.
    :param kwargs: :class:`FMEFileCache` constructor keyword arguments.
    """
    if not cache_root_path:
        cache_root_path = tempfile.gettempdir()
    cache_path = os.path.join(cache_root_path, cache_name)
    # If size limit not specified, get it from FME Workbench Options.
    if 'size_limit' not in kwargs:
        kwargs['size_limit'] = fme_configured_cache_size()
    try:
        return FMEFileCache(cache_path, logger=logger, **kwargs)
    except DatabaseError:
        shutil.rmtree(cache_path)
        return FMEFileCache(cache_path, logger=logger, **kwargs)


def fme_configured_cache_size(cache_properties=None):
    """Get cache size from FME Workbench Options, in bytes.

    :param dict cache_properties: Meant for debugging. If not specified, then config is obtained from fmeobjects.
    :return: Cache size from FME Workbench Options, in bytes. If value not present, assume 8 GiB.
    """
    if not cache_properties:
        from fmeobjects import FMESession  # Lazy load fmeobjects.
        cache_properties = stringArrayToDict(FMESession().getProperties(
            FME_WEB_FILE_CACHE_SIZE_PROPERTY_CATEGORY, []))

    cache_size_GB = float(
        cache_properties.get(FME_WEB_FILE_CACHE_SIZE_KEY, 8.0))
    return int(cache_size_GB * pow(1024, 3))


class FMEFileCache(Cache):
    """A file-based cache for caching files, with FME use cases in mind. Built
    on top of :class:`diskcache.Cache`. The superclass transparently handles
    cache expiry, eviction policies, culling, and size caps. It defaults to a
    maximum cache size of 1GB and a Least Recently Used eviction policy.

    This class provides additional setter and getter methods for working with whole files.
    These are intended for FME readers that perform expensive file downloads from web services,
    so that subsequent translations don't need to re-download the same files.
    For performance, hard links are used whenever possible.

    Call :meth:`close` when the caller is finished using the cache.
    This should be tied to your caller's lifecycle. Alternatively, use this class with a context manager.

    Note that writes are blocking, though this should not be a concern in most use cases.
    """

    def __init__(self, directory, logger=None, **kwargs):
        """
      :param str directory: Cache directory.
      :param Logger logger: Emit debug messages to this log.
      :param kwargs: Same as for :class:`diskcache.Cache`.
      """
        # PR74551: Hard-code cache eviction policy.
        # Other policies make reads request exclusive SQLite locks, which can fail on Mac. (PR74551)
        kwargs['eviction_policy'] = 'least-recently-stored'

        try:
            super(FMEFileCache, self).__init__(directory, **kwargs)
        except DatabaseError:
            # This can happen if the cache was previously opened by a newer Python.
            # Unrecoverable. Close the database connection so that caller can delete the cache directory and retry.
            self.close()
            raise

        # Cache config constructor arguments are only used when a cache is first created.
        # Re-apply these arguments now in case we're working with an existing cache.
        for setting in ('eviction_policy', 'size_limit', 'cull_limit'):
            if setting in kwargs:
                self.reset(setting, kwargs[setting])

        # Disable global stats, as they make reads request exclusive SQLite locks, which can fail on Mac. (PR74551)
        self.stats(enable=False)

        self._log = logger if logger else logging.getLogger(
            FMEFileCache.__name__)
        self._debugmsg("Opened cache at '%s', size limit %d B", directory,
                       kwargs.get('size_limit', 0))
        # Track some stats at the instance level. Superclass only tracks hits and misses at a global, persistent level.
        # These are prefixed with `instance_` because superclass has some of these members already.
        self.instance_hits, self.instance_misses = 0, 0
        self.instance_files_stored, self.instance_bytes_stored = 0, 0

    def _debugmsg(self, msg, *args):
        self._log.debug("CACHE: " + msg, *args)

    def read(self, key):
        try:
            handle = super(FMEFileCache, self).read(key)
            self.instance_hits += 1
            return handle
        except KeyError:
            self.instance_misses += 1
            raise

    def set_from_file(self, key, src_file_path, expire=None, tag=None):
        """Copy a file into the cache. Any existing value at the given key will
        be replaced. To conserve disk space, an attempt is made to replace the
        source file with a hard link to the newly cached copy.

        When downloading a file from the internet, it's possible to stream the response into the cache.
        This is not recommended, as cache writes are blocking and may have transaction timeouts.
        Files should first be downloaded completely, and then copied into the cache.

        :param str key: Key to set. Must be a valid filename. Any existing value is overwritten.
        :param str src_file_path: Copy the file at this path into the cache.
        :param int expire: Seconds until key expires. Default: never expires.
        :type tag: str or None
        :param tag: Text to associate with key. Default: None.
        :return: True if item was set.
        :rtype: bool
        """
        item_bytes = os.path.getsize(src_file_path)
        if item_bytes > self.size_limit:
            self._debugmsg(
                "Ignoring attempt to insert '%s', which exceeds cache size",
                key)
            return False

        self._debugmsg("Setting value of '%s' using '%s'", key, src_file_path)
        with open(src_file_path, 'rb') as src:
            self.instance_bytes_stored += item_bytes
            self.instance_files_stored += 1
            # Superclass source shows that set() always returns True.
            was_set = self.set(key, src, read=True, expire=expire, tag=tag)

        # Try to replace source file with a hard link to the cached copy.
        if was_set:
            self._debugmsg("Replacing '%s' with hard link to value of '%s'",
                           src_file_path, key)
            tmp_original = src_file_path + '.tmp'
            try:
                with self.read(key) as just_cached_file:
                    self.instance_hits -= 1  # Don't count this as a cache hit.
                    if os.path.isabs(just_cached_file.name):
                        os.rename(src_file_path, tmp_original)
                        hard_link(just_cached_file.name, src_file_path)
            except Exception as e:
                self._log.error("Hard link failed: %s", e)
            finally:
                # Deal with the temporarily-moved original.
                if os.path.exists(tmp_original):
                    if os.path.exists(src_file_path):
                        os.remove(tmp_original)  # Original isn't need anymore.
                    else:
                        os.rename(tmp_original, src_file_path
                                  )  # Hard link failed, so restore original.

        return was_set

    def get_tag(self, key):
        """Get the tag associated with the given key.

        :param str key: Key to get.
        :return: Tag value, or None if key doesn't exist or key has no tag.
        :rtype: str or None
        """
        open_file, tag = self.get(key, read=True, tag=True)
        if open_file:
            open_file.close()
        return tag

    def get_file_copy(self, key, dest_file_path=None):
        """Given a key, save a copy of its value as a file at a given location.
        The copy is either a true copy, or a hard link. The caller owns the it
        and is responsible for its deletion.

        The most common use case for this method is to obtain a path to pass as the dataset to an FME raster reader,
        with the `DELETE_SOURCE_ON_CLOSE` reader directive to hand the responsibility for file deletion to that reader.

        :param str key: Key to get.
        :param str dest_file_path: Destination path to save the file.
           If not specified then an appropriate one is generated, with filename as the key.
        :return: Absolute path to a copy of the file for the given key. Same as `dest_file_path`, if provided.
        :raises KeyError: If key does not exist.
        """
        with self.read(key) as cached_file:
            if not dest_file_path:
                fd, dest_file_path = tempfile.mkstemp(suffix=key)
                os.close(fd)

            cached_as_file = os.path.isabs(cached_file.name)
            hard_link_failed = False
            if cached_as_file:
                # Try to make a hard link to the cached file.
                try:
                    self._debugmsg("Hard-linking value of '%s' as '%s'", key,
                                   dest_file_path)
                    hard_link(cached_file.name, dest_file_path)
                except Exception as e:
                    self._debugmsg("Hard link failed: %s", e)
                    hard_link_failed = True

            # Fallback to file copy if cached data has no filesystem path or hard-linking failed.
            if not cached_as_file or hard_link_failed:
                self._debugmsg("Copying value of '%s' to '%s'", key,
                               dest_file_path)
                with open(dest_file_path, 'wb') as out_file:
                    try:
                        while True:
                            chunk = cached_file.read(8192)
                            if not chunk:
                                break
                            out_file.write(chunk)
                    except:
                        out_file.close()
                        if os.path.exists(dest_file_path):
                            os.remove(dest_file_path)
                        raise

            return dest_file_path

    def close(self):
        """Close the cache connection, and log a debug message with statistics
        about this session."""
        try:
            self._debugmsg(
                "%d hits, %d misses, stored %d items totalling %s. Capacity: %s/%s.",
                self.instance_hits,
                self.instance_misses,
                self.instance_files_stored,
                pretty_file_size(self.instance_bytes_stored),
                pretty_file_size(self.volume()),
                pretty_file_size(self.size_limit),
            )
            if self.instance_bytes_stored > self.size_limit:
                self._debugmsg(
                    "Bytes written to the cache exceeds max cache size. Consider increasing max cache size."
                )
        except AttributeError:
            pass  # Superclass constructor calls close on itself, so members may not exist yet.
        super(FMEFileCache, self).close()


def hard_link(link_to, link_from):
    """Create a hard link on Mac, Linux, and Windows. Fills in Windows support
    prior to Python 3.2.

    :param str link_to: Link to this file.
    :param str link_from: Create the hard link at this path. If the destination file already exists, it will be deleted.
    :raises OSError: If OS doesn't support hard links.
    :raises subprocess.CalledProcessError: If on Python < 3.2 and Windows, and the `mklink` command failed.
       There are many potential causes of failure, but a common one is that mklink requires Administrator permissions
       prior to Windows 10 / Windows Server 2016.
    :raises: Anything :func:`os.link` may raise.
    """
    if os.path.exists(link_from):
        os.remove(link_from)  # Hard link location can't already exist.

    if os.name == 'posix':
        return os.link(link_to, link_from)
    elif os.name == 'nt':
        if sys.version_info >= (3, 2):
            return os.link(link_to, link_from)
        # https://technet.microsoft.com/en-us/library/cc753194(v=ws.11).aspx
        # check_output to grab stdout so it doesn't go to log.
        subprocess.check_output(
            ['mklink', '/H', link_from, link_to], shell=True)
        return
    raise OSError("Cannot create hard links on this OS.")


def pretty_file_size(size_b):
    """Convert size in bytes to something nicer, like '1.3 GiB'. IEC prefixes
    (1024), not SI (1000).

    :param int size_b: Size in bytes.
    :return: String representation, using largest appropriate prefix.
    """
    running_size = size_b
    its = 0
    while running_size // 1024:
        running_size /= 1024
        its += 1

    prefixes = ('', 'Ki', 'Mi', 'Gi', 'Ti')
    return '{:1.1f} {}B'.format(running_size, prefixes[min(its,
                                                           len(prefixes))])
