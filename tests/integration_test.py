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

    # fixme: on travis calling systemctl emits error "Failed to connect to bus: No such file or directory"
    cmd(["create", "./tests/trivial_script_0.py", "--nolist"])

    unit_info = list_unit_info()

    # should be true when fixed
    assert unit_info == {"trivial_script_0_py": (False, False, "")}

    cmd(["create", "./tests/trivial_script_1.py", "--nolist"])

    unit_info = list_unit_info()
    # should all be true when fixed
    assert unit_info == {
        "trivial_script_0_py": (False, False, ""),
        "trivial_script_1_py": (False, False, ""),
    }

    cmd(["delete", "trivial_script_1_py"])

    unit_info = list_unit_info()
    # should all be true when fixed
    assert unit_info == {"trivial_script_0_py": (False, False, "")}
