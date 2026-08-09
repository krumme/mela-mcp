def test_package_imports_with_version():
    import mela_mcp
    assert isinstance(mela_mcp.__version__, str)
    assert mela_mcp.__version__
