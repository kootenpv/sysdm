from os import environ
import pytest
from sysdm.__main__ import _main


def cmd(args):
    """
    use cli

    :type args: list
    """
    _main([...] + args)


def test_integration():
    """
    test a series of operations
    """
    if not environ.get("TRAVIS", False):
        pytest.skip("Integration test only performed on travis")

    cmd(["create", "./tests/trivial_script_0.py", "--nolist"])

    cmd(["create", "./tests/trivial_script_1.py", "--nolist"])
