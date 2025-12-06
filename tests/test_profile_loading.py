#!/usr/bin/env python3
"""Phase 0.4: Test that profile module sources use shadow URL rewriting.

This test validates that when AMPLIFIER_GIT_HOST is set, modules referenced
in profiles via git+https://github.com/... URLs are downloaded from the
shadow Gitea server instead.
"""

import os
import sys


def test_gitsource_rewriting():
    """Test that GitSource rewrites URLs when AMPLIFIER_GIT_HOST is set."""
    from amplifier_module_resolution.sources import GitSource

    # Test with shadow host set
    os.environ["AMPLIFIER_GIT_HOST"] = "http://gitea:3000"

    # Simulate what a profile source field would contain
    profile_source = "git+https://github.com/microsoft/amplifier-module-loop-basic@main"

    # Parse the source (this is what the resolver does)
    source = GitSource.from_uri(profile_source)

    # Check URL rewriting
    effective_url = source._get_effective_url()  # type: ignore[attr-defined]
    expected = "http://gitea:3000/amplifier/amplifier-module-loop-basic"

    print("Test: GitSource URL Rewriting")
    print(f"  Profile source: {profile_source}")
    print(f"  Parsed URL:     {source.url}")
    print(f"  Effective URL:  {effective_url}")

    assert effective_url == expected, f"Expected {expected}, got {effective_url}"
    print("  ✅ PASS: URL correctly rewritten for shadow")
    return True


def test_module_download_from_shadow():
    """Test that modules are actually downloaded from shadow Gitea."""
    from amplifier_module_resolution.sources import GitSource

    os.environ["AMPLIFIER_GIT_HOST"] = "http://gitea:3000"

    # Use a module we know is published to shadow
    source = GitSource.from_uri("git+https://github.com/microsoft/amplifier-module-loop-basic@main")

    print("\nTest: Module Download from Shadow")
    print(f"  Resolving: {source.url}@{source.ref}")

    try:
        path = source.resolve()
        print(f"  Downloaded to: {path}")

        # Verify it has Python files
        py_files = list(path.glob("**/*.py"))
        print(f"  Found {len(py_files)} Python files")

        assert len(py_files) > 0, "No Python files found in downloaded module"
        print("  ✅ PASS: Module downloaded successfully from shadow!")
        return True

    except Exception as e:
        print(f"  ❌ FAIL: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_resolver_with_profile_hint():
    """Test that StandardModuleSourceResolver uses profile hint with rewriting."""
    from amplifier_module_resolution.resolvers import StandardModuleSourceResolver
    from amplifier_module_resolution.sources import GitSource

    os.environ["AMPLIFIER_GIT_HOST"] = "http://gitea:3000"

    resolver = StandardModuleSourceResolver()

    # Simulate a profile hint (what comes from profile's source field)
    profile_hint = "git+https://github.com/microsoft/amplifier-module-context-simple@main"

    print("\nTest: Resolver with Profile Hint")
    print("  Module ID: context-simple")
    print(f"  Profile hint: {profile_hint}")

    try:
        # The resolver should use the profile hint and GitSource should rewrite
        result = resolver.resolve("context-simple", profile_hint=profile_hint)

        if result:
            print(f"  Resolved to: {result}")

            # If result is a GitSource, resolve it to get the path
            if isinstance(result, GitSource):
                # Check that URL rewriting is applied
                effective_url = result._get_effective_url()  # type: ignore[attr-defined]
                print(f"  Effective URL: {effective_url}")
                assert "gitea:3000" in effective_url, "URL not rewritten for shadow"

                # Resolve to path
                path = result.resolve()
                print(f"  Downloaded to: {path}")
                py_files = list(path.glob("**/*.py"))
            else:
                # Result is already a path
                py_files = list(result.glob("**/*.py"))

            print(f"  Found {len(py_files)} Python files")
            assert len(py_files) > 0, "No Python files found"
            print("  ✅ PASS: Resolver used profile hint with shadow rewriting!")
            return True
        else:
            print("  ❌ FAIL: Resolver returned None")
            return False

    except Exception as e:
        print(f"  ❌ FAIL: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_provider_module():
    """Test provider module can be downloaded from shadow."""
    from amplifier_module_resolution.sources import GitSource

    os.environ["AMPLIFIER_GIT_HOST"] = "http://gitea:3000"

    source = GitSource.from_uri("git+https://github.com/microsoft/amplifier-module-provider-mock@main")

    print("\nTest: Provider Module from Shadow")
    print(f"  Resolving: {source.url}@{source.ref}")

    try:
        path = source.resolve()
        print(f"  Downloaded to: {path}")

        # Check for provider module structure
        py_files = list(path.glob("**/*.py"))
        print(f"  Found {len(py_files)} Python files")

        assert len(py_files) > 0, "No Python files found"
        print("  ✅ PASS: Provider module downloaded from shadow!")
        return True

    except Exception as e:
        print(f"  ❌ FAIL: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """Run all Phase 0.4 tests."""
    print("=" * 60)
    print("Phase 0.4: Profile Loading Tests")
    print("Testing shadow URL rewriting for profile module sources")
    print("=" * 60)
    print()

    results = []

    results.append(("GitSource URL Rewriting", test_gitsource_rewriting()))
    results.append(("Module Download from Shadow", test_module_download_from_shadow()))
    results.append(("Resolver with Profile Hint", test_resolver_with_profile_hint()))
    results.append(("Provider Module", test_provider_module()))

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
