"""Generic logic for disambiguation of feature types"""

from __future__ import absolute_import, division, print_function, unicode_literals

from fmeobjects import FMEException


class FeatureTypeNotFoundException(FMEException):
    """Exception for when the feature type wasn't matched to any record."""

    def __init__(self, msgNum, logPrefix, featureType):
        """
      :param int msgNum: The message number.
      :param str logPrefix: The log message prefix.
      :param str featureType: The feature type.
      """
        super(FeatureTypeNotFoundException, self).__init__(
            msgNum, [logPrefix, featureType])


class FeatureTypeAmbiguousException(FMEException):
    """Exception for when the feature type matches multiple records."""

    def __init__(self, msgNum, logPrefix, featureType, matchedRecords):
        """
      :param int msgNum: The message number.
      :param str logPrefix: The log message prefix.
      :param str featureType:  The feature type.
      :param list[str] matchedRecords: List of record names, each formatted for user display. *Not* a list of dicts.
      """
        matchDesc = ", ".join(matchedRecords)
        super(FeatureTypeAmbiguousException, self).__init__(
            msgNum, [logPrefix, featureType, matchDesc])


class Disambiguator(object):
    """Utility for disambiguating feature types."""
    def __init__(self, logger, logPrefix, msgNumForNotFoundException,
                 msgNumForNotFound, msgNumForFound,
                 msgNumForAmbiguousException):
        """
      :param Logger logger: Logging instance.
      :param int msgNumForNotFoundException: For when no match was found for the given value and is considered an error.
      :param int msgNumForNotFound: For when no match was found for the given value.
      :param int msgNumForFound: For when when a single exact match is found.
      :param int msgNumForAmbiguousException: Exception message for when there is more than one match by name.
      """
        self._logger = logger
        self.logPrefix = logPrefix
        self.msgNumForNotFoundException = msgNumForNotFoundException
        self.msgNumForNotFound = msgNumForNotFound
        self.msgNumForFound = msgNumForFound
        self.msgNumForAmbiguousException = msgNumForAmbiguousException

    @staticmethod
    def joinNameAndId(record, includeId=True):
        """Join name and ID if ``includeID`` is True.

      :param dict record: Must have keys `name` and `id`.
      :param bool includeId: whether the ID should be included too.
      :rtype: str
      """
        if includeId:
            return "%(name)s (%(id)s)" % record
        return record['name']

    @staticmethod
    def splitIntoNameAndId(joinedName):
        """Given a joined name and/or ID, split it into the name and ID parts.
        If a name and ID aren't both found, consider the joined name to be the
        name, and the ID to be None.

        :param str joinedName: The joined name and/or ID.
        :returns: Dictionary with keys `name` and `id`.
        :rtype: dict
        """
        name, idValue = None, None
        idLeftBound = joinedName.rfind('(')
        idRightBound = joinedName.rfind(')')
        if idLeftBound > -1 and idRightBound > -1 and idRightBound - idLeftBound > 1:
            idValue = joinedName[idLeftBound + 1:idRightBound]
            name = joinedName[:idLeftBound].strip()
        else:
            name = joinedName
        if len(name) == 0:
            name = None

        return {'name': name, 'id': idValue}

    @staticmethod
    def isMatchByName(featureType, valueParts, record):
        """Returns True if the record name appears in the joined name/ID of the feature type.

        :param str featureType: A feature type
        :param dict valueParts: Dictionary with keys `name` and `id` from :meth:`splitIntoNameAndId`.
        :param dict record: Dictionary with keys `name` and `id`.
        :rtype: bool
        """
        return record['name'] in (valueParts['name'], featureType)

    def disambiguate(self, value, dataSource, errorIfNotFound):
        """Generic logic for disambiguating a feature service directive value
        or feature type, and handling/raising the possible error cases.

        :param str value: Value to disambiguate. Usually a feature type.
        :param function dataSource: A function that takes no arguments. When called, it returns a list of dicts,
           each of which contain 'name' and 'id' as keys.
        :param bool errorIfNotFound: If true, an exception is raised if a match is not found.
           If false, the message is logged with INFO severity if a match is not found.
        :returns: Dictionary with keys `name` and `id`.
        :rtype: dict[str]
        :raises FeatureTypeNotFoundException: If feature type doesn't match anything, and `errorIfNotFound` was true.
        :raises FeatureTypeAmbiguousException: If feature type matches more than one record.
        """
        parts = self.splitIntoNameAndId(value)

        existingRecords = dataSource()
        recordsMatchedByName = []
        for record in existingRecords:
            record_id = str(record['id'])
            if record_id in (parts['id'], parts['name']):
                # Exact unambiguous match by ID. Short-circuit and return.
                self._logger.logMessage(
                    self.msgNumForFound,
                    [self.logPrefix, record['name'], record_id, value])
                return record
            if self.isMatchByName(value, parts, record):
                # Collect all matches by name (and path, if a path was specified).
                recordsMatchedByName.append(record)

        if len(recordsMatchedByName) == 0:
            # No match. Either log as INFO severity, or raise exception.
            if errorIfNotFound:
                raise FeatureTypeNotFoundException(
                    self.msgNumForNotFoundException, self.logPrefix, value)
            else:
                self._logger.logMessage(self.msgNumForNotFound,
                                        [self.logPrefix, value])
                return
        elif len(recordsMatchedByName) == 1:
            # Exactly one match by name.
            matched = recordsMatchedByName[0]
            self._logger.logMessage(
                self.msgNumForFound,
                [self.logPrefix, matched['name'], matched['id'], value])
            return matched
        else:
            # Multiple matches by name. Raise exception.
            matchedRecordStrings = [
                self.joinNameAndId(record, includeId=True)
                for record in recordsMatchedByName
            ]
            raise FeatureTypeAmbiguousException(
                self.msgNumForAmbiguousException, self.logPrefix, value,
                matchedRecordStrings)
