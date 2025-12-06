#!/usr/bin/env python3
"""Phase 0.5: Test that collection installs use shadow URL rewriting.

This test validates that when AMPLIFIER_GIT_HOST is set, collections installed
via git+https://github.com/... URLs are downloaded from the shadow Gitea server.
"""

import os
import sys
import tempfile
from pathlib import Path


def test_gitsource_install_to():
    """Test that GitSource.install_to() uses shadow URL rewriting."""
    import asyncio

    from amplifier_module_resolution.sources import GitSource

    os.environ["AMPLIFIER_GIT_HOST"] = "http://gitea:3000"

    # Use a module we know is published to shadow
    source = GitSource.from_uri("git+https://github.com/microsoft/amplifier-module-loop-basic@main")

    print("Test: GitSource.install_to() with Shadow Rewriting")
    print(f"  Source URL: {source.url}")
    effective = source._get_effective_url()  # type: ignore[attr-defined]
    print(f"  Effective URL: {effective}")

    # Verify URL rewriting
    assert "gitea:3000" in effective, f"URL not rewritten: {effective}"
    print("  ✅ URL correctly rewritten for shadow")

    # Test install_to() - this is what collection installer uses
    with tempfile.TemporaryDirectory() as tmpdir:
        target = Path(tmpdir) / "test-install"
        print(f"  Installing to: {target}")

        try:
            # Run the async install
            asyncio.run(source.install_to(target))

            # Verify installation
            assert target.exists(), "Target directory not created"
            py_files = list(target.glob("**/*.py"))
            print(f"  Found {len(py_files)} Python files")
            assert len(py_files) > 0, "No Python files installed"

            print("  ✅ PASS: install_to() worked with shadow rewriting!")
            return True

        except Exception as e:
            print(f"  ❌ FAIL: {e}")
            import traceback

            traceback.print_exc()
            return False


def test_collection_like_install():
    """Test a collection-style installation pattern."""
    import asyncio

    from amplifier_module_resolution.sources import GitSource

    os.environ["AMPLIFIER_GIT_HOST"] = "http://gitea:3000"

    # Simulate collection install (uses same GitSource pattern)
    collection_url = "git+https://github.com/microsoft/amplifier-collection-recipes@main"

    print("\nTest: Collection-Style Installation")
    print(f"  Collection URL: {collection_url}")

    try:
        source = GitSource.from_uri(collection_url)
        effective = source._get_effective_url()  # type: ignore[attr-defined]
        print(f"  Effective URL: {effective}")

        assert "gitea:3000" in effective, f"URL not rewritten: {effective}"
        print("  ✅ URL correctly rewritten for shadow")

        # Install to temp directory
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "collection-test"
            print(f"  Installing to: {target}")

            asyncio.run(source.install_to(target))

            assert target.exists(), "Collection not installed"

            # Collections typically have profiles/ or modules/ directories
            contents = list(target.iterdir())
            print(f"  Installed contents: {[c.name for c in contents[:5]]}...")

            print("  ✅ PASS: Collection installed from shadow!")
            return True

    except Exception as e:
        print(f"  ❌ FAIL: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_multiple_modules_install():
    """Test installing multiple modules (simulating collection with dependencies)."""

    from amplifier_module_resolution.sources import GitSource

    os.environ["AMPLIFIER_GIT_HOST"] = "http://gitea:3000"

    modules = [
        "git+https://github.com/microsoft/amplifier-module-loop-basic@main",
        "git+https://github.com/microsoft/amplifier-module-context-simple@main",
        "git+https://github.com/microsoft/amplifier-module-provider-mock@main",
    ]

    print("\nTest: Multiple Modules Installation")

    results = []
    for module_url in modules:
        source = GitSource.from_uri(module_url)
        effective = source._get_effective_url()  # type: ignore[attr-defined]

        # Extract module name
        module_name = source.url.split("/")[-1]
        print(f"  {module_name}:")
        print(f"    Effective: {effective}")

        if "gitea:3000" in effective:
            results.append(True)
            print("    ✅ URL rewritten")
        else:
            results.append(False)
            print(f"    ❌ URL not rewritten: {effective}")

    if all(results):
        print("  ✅ PASS: All modules use shadow URLs!")
        return True
    else:
        print("  ❌ FAIL: Some modules not rewritten")
        return False


def test_uri_property_preserved():
    """Test that GitSource.uri property returns original URL (for lock files)."""
    from amplifier_module_resolution.sources import GitSource

    os.environ["AMPLIFIER_GIT_HOST"] = "http://gitea:3000"

    original_uri = "git+https://github.com/microsoft/amplifier-module-loop-basic@main"
    source = GitSource.from_uri(original_uri)

    print("\nTest: URI Property Preservation")
    print(f"  Original URI: {original_uri}")
    print(f"  source.uri: {source.uri}")

    # The uri property should return the ORIGINAL URL (for lock files)
    # NOT the rewritten URL
    assert source.uri == original_uri, f"URI changed: {source.uri}"
    print("  ✅ PASS: URI preserved (for lock file recording)")
    return True


def main():
    """Run all Phase 0.5 tests."""
    print("=" * 60)
    print("Phase 0.5: Collection Testing")
    print("Testing shadow URL rewriting for collection installs")
    print("=" * 60)
    print()

    results = []

    results.append(("GitSource.install_to()", test_gitsource_install_to()))
    results.append(("Collection-Style Install", test_collection_like_install()))
    results.append(("Multiple Modules Install", test_multiple_modules_install()))
    results.append(("URI Property Preserved", test_uri_property_preserved()))

    print()
    print("=" * 60)
    print("Summary")
    print("=" * 60)

    passed = sum(1 for _, r in results if r)
    total = len(results)

    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status}: {name}")

    print()
    print(f"Total: {passed}/{total} tests passed")

    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
