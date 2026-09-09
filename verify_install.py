"""
Quick verification script to test package installation.
Run this after installing the package to verify everything works.
"""

import sys


def test_imports():
    """Test that all main modules can be imported."""
    
    print("Testing code_fixer package imports...")
    print("="*80)
    
    try:
        import code_fixer
        print(f"✓ code_fixer v{code_fixer.__version__}")
    except ImportError as e:
        print(f"✗ Failed to import code_fixer: {e}")
        return False
    
    modules = [
        'github_utils',
        'vector_store',
        'prompts',
        'patch_output',
        'swe_bench',
        'io_utils',
        'log',
        'process_layer',
    ]
    
    failed = []
    for module_name in modules:
        try:
            module = getattr(code_fixer, module_name)
            print(f"✓ code_fixer.{module_name}")
        except AttributeError as e:
            print(f"✗ code_fixer.{module_name}: {e}")
            failed.append(module_name)
    
    print("\n" + "="*80)
    
    if failed:
        print(f"\n✗ Failed to import {len(failed)} module(s): {', '.join(failed)}")
        return False
    else:
        print("\n✓ All modules imported successfully!")
        return True


def test_key_functions():
    """Test that key functions are available."""
    
    print("\nTesting key functions...")
    print("="*80)
    
    from code_fixer import (
        build_vector_store,
        download_codebase,
        compute_patch_metrics,
    )
    
    functions = [
        ('build_vector_store', build_vector_store),
        ('download_codebase', download_codebase),
        ('compute_patch_metrics', compute_patch_metrics),
    ]
    
    for name, func in functions:
        if callable(func):
            print(f"✓ {name}() is callable")
        else:
            print(f"✗ {name} is not callable")
            return False
    
    print("\n" + "="*80)
    print("\n✓ All key functions are available!")
    return True


def test_models():
    """Test that Pydantic models can be imported."""
    
    print("\nTesting Pydantic models...")
    print("="*80)
    
    try:
        from code_fixer.patch_output import PatchSuggestions, PatchSnippet, DiffViewEdits
        print("✓ PatchSuggestions")
        print("✓ PatchSnippet")
        print("✓ DiffViewEdits")
    except ImportError as e:
        print(f"✗ Failed to import models: {e}")
        return False
    
    print("\n" + "="*80)
    print("\n✓ All models imported successfully!")
    return True


def main():
    print("\n")
    print("╔" + "="*78 + "╗")
    print("║" + " "*20 + "CODE FIXER PACKAGE VERIFICATION" + " "*26 + "║")
    print("╚" + "="*78 + "╝")
    print("\n")
    
    tests = [
        test_imports,
        test_key_functions,
        test_models,
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"\n✗ Test failed with exception: {e}")
            import traceback
            traceback.print_exc()
            results.append(False)
    
    print("\n" + "="*80)
    print("FINAL RESULT")
    print("="*80)
    
    if all(results):
        print("\n✓✓✓ All tests passed! Package is ready to use. ✓✓✓\n")
        return 0
    else:
        print("\n✗✗✗ Some tests failed. Please check the errors above. ✗✗✗\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
