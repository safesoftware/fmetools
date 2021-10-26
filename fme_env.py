"""
A CLI script to set up a virtualenv to work with FME.
"""
import os
import argparse
import shutil
import sys


fme_home = os.environ.get("FME_HOME")

parser = argparse.ArgumentParser(
    description="Configure the current virtualenv so that it can load the "
    "FME Python SDK and the set of Python libraries included with FME."
)
parser.add_argument(
    "--fme-home",
    default=fme_home,
    help="FME install directory. Default: FME_HOME environment variable",
)

site_packages_dir = os.path.join(sys.prefix, "Lib", "site-packages")

if __name__ == "__main__":
    # Running as the CLI utility
    if os.path.basename(sys.prefix) not in ("env", "venv", ".env", ".venv"):
        raise ValueError("Python doesn't seem to be running in a virtualenv. Aborting")

    args = parser.parse_args()
    if not os.path.isdir(site_packages_dir):
        raise ValueError("Couldn't find " + site_packages_dir)

    if not args.fme_home:
        raise ValueError(
            "FME_HOME environment variable not defined, so --fme-home must be given"
        )
    print("Using FME install dir: " + args.fme_home)
    if not os.path.isdir(args.fme_home):
        raise ValueError("FME_HOME is not a directory")

    leaf_dir = "python%s%s" % (sys.version_info.major, sys.version_info.minor)
    paths_to_add = [
        "#" + args.fme_home,
        os.path.join(args.fme_home, "python"),
        os.path.join(args.fme_home, "python", "python%s" % sys.version_info.major),
        os.path.join(args.fme_home, "python", leaf_dir),
        os.path.join(args.fme_home, "fmeobjects", leaf_dir),
    ]

    dst_pth = os.path.join(site_packages_dir, "fme_env.pth")
    print("Writing " + dst_pth)
    with open(dst_pth, "w") as f:
        for path in paths_to_add:
            f.write(path + "\n")
        f.write("import fme_env\n")

    dst_py = os.path.join(site_packages_dir, "fme_env.py")
    print("Writing " + dst_py)
    shutil.copyfile(__file__, dst_py)

    print("\nThis virtualenv is now set up for access to FME and fmeobjects.")
    print("If the FME install location changes, re-run this script to update paths.")
else:
    # Running in site-packages as part of interpreter's site setup
    # First line from .pth is FME_HOME
    src_pth = os.path.join(site_packages_dir, "fme_env.pth")
    with open(src_pth, "r") as f:
        fme_home = f.readline().strip("#\n ")
    if fme_home:
        if hasattr(os, "add_dll_directory"):
            os.add_dll_directory(fme_home)
        else:
            os.environ["PATH"] = fme_home + ";" + os.environ["PATH"]
