""" File unrelated to the package, except for convenience in deploying """
import os
import re
import subprocess

# Micro version is the commit count, so the published version always maps to a commit.
commit_count = subprocess.check_output(["git", "rev-list", "--all", "--count"]).decode().strip()

with open("pyproject.toml") as f:
    pyproject = f.read()

major, minor, _ = re.search(r'^version = "(\d+)\.(\d+)\.(\d+)"', pyproject, re.M).groups()
version = "{}.{}.{}".format(major, minor, commit_count)

pyproject = re.sub(r'^version = "[0-9.]+"', 'version = "{}"'.format(version), pyproject, count=1, flags=re.M)
with open("pyproject.toml", "w") as f:
    f.write(pyproject)

with open("sysdm/__init__.py") as f:
    init = f.read()

with open("sysdm/__init__.py", "w") as f:
    f.write(re.sub('__version__ = "[0-9.]+"', '__version__ = "{}"'.format(version), init))

print("Building {}".format(version))
os.system("rm -rf dist/")
if os.system("python -m build") != 0:
    raise SystemExit("build failed")
if os.system("twine check dist/*") != 0:
    raise SystemExit("twine check failed")
os.system("twine upload dist/*")
