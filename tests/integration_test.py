# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from os import environ
import pytest

from sysdm import list_unit_info
from sysdm.__main__ import _main


def cmd(args):
    """
    use cli

    :type args: list
    """
    _main([""] + args)


def test_integration():
    """
    test a series of operations
    """
    if not environ.get("TRAVIS", False):
        pytest.skip("It's recommended that integration tests only performed on travis")

    cmd(["create", "./tests/trivial_script_0.py", "--nolist"])

    unit_info = list_unit_info()

    assert unit_info == {"trivial_script_0_py": [True, True, ""]}

    cmd(["create", "./tests/trivial_script_1.py", "--nolist"])

    unit_info = list_unit_info()
    assert unit_info == {
        "trivial_script_0_py": [True, True, ""],
        "trivial_script_1_py": [True, True, ""],
    }

    cmd(["delete", "trivial_script_1_py"])

    unit_info = list_unit_info()
    assert unit_info == {"trivial_script_0_py": [True, True, ""]}
