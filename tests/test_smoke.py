"""Smoke test to verify the package can be imported."""


def test_import_main():
    """Test that the main module can be imported."""
    from machine_setup import main

    assert hasattr(main, "main")
