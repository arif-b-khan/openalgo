#!/usr/bin/env python3
"""
OpenAlgo .env File Synchronization Script

Intelligently synchronizes .env from .sample.env while:
- Preserving customized values (detected by comparing with .sample.env)
- Removing orphaned properties (in .env but not in .sample.env)
- Preserving all comments/documentation from .sample.env
- Working cross-platform (Windows & Linux)

Usage:
    python sync_env.py              # Sync with backup (default)
    python sync_env.py --dry-run    # Show changes without modifying
    python sync_env.py --force      # Skip confirmation prompts
    python sync_env.py --help       # Show help

Author: OpenAlgo
License: MIT
"""

import argparse
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Tuple, List


class EnvParser:
    """Parser for .env files that preserves comments, blank lines, and structure."""

    def __init__(self, file_path: Path):
        self.file_path = file_path
        self.lines: List[str] = []
        self.properties: Dict[str, str] = {}
        self.property_indices: Dict[str, int] = {}
        self.commented_properties: Dict[str, str] = {}  # Properties that are commented out
        self.parse()

    def parse(self) -> None:
        """Parse .env file, extracting properties while preserving structure."""
        if not self.file_path.exists():
            return

        with open(self.file_path, 'r', encoding='utf-8') as f:
            self.lines = f.readlines()

        for idx, line in enumerate(self.lines):
            stripped = line.strip()
            
            # Skip blank lines when looking for properties
            if not stripped:
                continue

            # Handle commented property lines: # KEY = 'value'
            if stripped.startswith('#') and '=' in stripped:
                comment_part = stripped[1:].strip()  # Remove # and leading space
                key, _, value = comment_part.partition('=')
                key = key.strip()
                value = value.strip()
                
                if key and value and key.isupper():  # Likely a property, not regular comment
                    self.commented_properties[key] = value
                continue

            # Parse property line: KEY = 'value' or KEY="value" or KEY=value
            if '=' in stripped and not stripped.startswith('#'):
                key, _, value = stripped.partition('=')
                key = key.strip()
                value = value.strip()
                
                if key and value:
                    self.properties[key] = value
                    self.property_indices[key] = idx

    def get(self, key: str, default: str = '') -> str:
        """Get property value by key."""
        return self.properties.get(key, default)

    def get_all_properties(self) -> Dict[str, str]:
        """Get all parsed properties."""
        return self.properties.copy()
    
    def get_commented_properties(self) -> Dict[str, str]:
        """Get all commented-out properties."""
        return self.commented_properties.copy()


class EnvSyncer:
    """Synchronizes .env from .sample.env while preserving all existing values."""

    def __init__(self, sample_path: Path, env_path: Path):
        self.sample_path = sample_path
        self.env_path = env_path
        self.sample_parser = EnvParser(sample_path)
        self.env_parser = EnvParser(env_path)
        
        self.added_properties: Dict[str, str] = {}      # New properties from .sample.env
        self.updated_properties: Dict[str, Tuple[str, str]] = {}  # (old_value, new_value) from .sample.env
        self.preserved_properties: Dict[str, str] = {}  # Kept from .env
        self.removed_properties: List[str] = []         # Orphaned from .env
        self.commented_properties: Dict[str, str] = {}  # Commented properties from .env to preserve

    def analyze(self) -> None:
        """Analyze differences between .sample.env and .env."""
        sample_props = self.sample_parser.get_all_properties()
        env_props = self.env_parser.get_all_properties()
        
        # Preserve commented properties from old .env
        self.commented_properties = self.env_parser.get_commented_properties()

        # Check each property in .sample.env
        for key, sample_value in sample_props.items():
            if key not in env_props:
                # New property in .sample.env (not in old .env)
                self.added_properties[key] = sample_value
            else:
                env_value = env_props[key]
                if env_value == sample_value:
                    # Value unchanged (still same as sample)
                    self.preserved_properties[key] = env_value
                else:
                    # Value changed (different from sample)
                    # Special case: Always upgrade ENV_CONFIG_VERSION
                    if key == 'ENV_CONFIG_VERSION':
                        self.updated_properties[key] = (env_value, sample_value)
                        self.preserved_properties[key] = sample_value  # Use new version
                    else:
                        self.updated_properties[key] = (env_value, sample_value)
                        # But actually use the OLD value from .env (preserve user's value)
                        self.preserved_properties[key] = env_value

        # Find orphaned properties (in .env but not in .sample.env)
        for key in env_props:
            if key not in sample_props:
                self.removed_properties.append(key)

    def generate_new_env(self) -> str:
        """Generate new .env content based on .sample.env structure with preserved values."""
        result_lines: List[str] = []
        sample_props = self.sample_parser.get_all_properties()
        
        with open(self.sample_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        # Process .sample.env structure with values from .env
        for line in lines:
            stripped = line.strip()

            # Copy comments and blank lines as-is
            if not stripped or stripped.startswith('#'):
                result_lines.append(line)
                continue

            # Handle property lines
            if '=' in stripped:
                key, _, _ = stripped.partition('=')
                key = key.strip()

                if key in sample_props:
                    # Use value from .env if available (preserve old value)
                    # Otherwise use value from .sample.env
                    if key in self.preserved_properties:
                        value = self.preserved_properties[key]
                    else:
                        value = sample_props[key]

                    # Reconstruct line with proper formatting
                    result_lines.append(f"{key} = {value}\n")
                # Skip keys that are not in .sample.env (orphaned)
            else:
                result_lines.append(line)

        # Append preserved commented properties at the end
        if self.commented_properties:
            result_lines.append("\n")
            result_lines.append("# " + "=" * 68 + "\n")
            result_lines.append("# CUSTOM/COMMENTED PROPERTIES (Preserved from previous .env)\n")
            result_lines.append("# " + "=" * 68 + "\n")
            for key in sorted(self.commented_properties.keys()):
                value = self.commented_properties[key]
                result_lines.append(f"# {key} = {value}\n")

        return ''.join(result_lines)

    def get_summary(self) -> str:
        """Get human-readable summary of changes."""
        lines = []
        lines.append("\n" + "=" * 70)
        lines.append("ENV SYNCHRONIZATION SUMMARY")
        lines.append("=" * 70)

        if self.added_properties:
            lines.append(f"\n📌 New properties (from .sample.env): {len(self.added_properties)}")
            for key in sorted(self.added_properties.keys()):
                value = self.added_properties[key]
                lines.append(f"   + {key:40s} = {value}")

        # Separate upgraded properties (like ENV_CONFIG_VERSION) from others
        upgraded_props = {}
        other_updated = {}
        for key, (old_val, new_val) in self.updated_properties.items():
            if key == 'ENV_CONFIG_VERSION':
                upgraded_props[key] = (old_val, new_val)
            else:
                other_updated[key] = (old_val, new_val)

        if upgraded_props:
            lines.append(f"\n🆙 Upgraded properties: {len(upgraded_props)}")
            for key in sorted(upgraded_props.keys()):
                old_val, new_val = upgraded_props[key]
                lines.append(f"   ⬆️  {key}")
                lines.append(f"      Old value: {old_val}")
                lines.append(f"      New value: {new_val}")

        if self.preserved_properties:
            lines.append(f"\n✅ Preserved values (from old .env): {len(self.preserved_properties)}")
            for key in sorted(self.preserved_properties.keys()):
                value = self.preserved_properties[key]
                # Truncate long values for readability
                display_value = value if len(value) <= 40 else value[:37] + "..."
                lines.append(f"   ✓ {key:40s} = {display_value}")

        if other_updated:
            lines.append(f"\n⚠️  Properties with new defaults (but keeping old values): {len(other_updated)}")
            for key in sorted(other_updated.keys()):
                old_val, new_val = other_updated[key]
                lines.append(f"   ⟲ {key}")
                lines.append(f"      Old .env value: {old_val}")
                lines.append(f"      New .sample.env: {new_val}")
                lines.append(f"      → Keeping: {old_val}")

        if self.removed_properties:
            lines.append(f"\n❌ Removed orphaned properties: {len(self.removed_properties)}")
            for key in sorted(self.removed_properties):
                lines.append(f"   - {key}")

        if self.commented_properties:
            lines.append(f"\n💬 Preserved commented properties: {len(self.commented_properties)}")
            for key in sorted(self.commented_properties.keys()):
                lines.append(f"   # {key}")

        if not (self.added_properties or self.preserved_properties or 
                self.updated_properties or self.removed_properties):
            lines.append("\n✅ No changes needed - .env is already in sync!")

        lines.append("\n" + "=" * 70 + "\n")
        return '\n'.join(lines)


def create_backup(file_path: Path) -> Path:
    """Create timestamped backup of .env file."""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = file_path.parent / f"{file_path.name}.backup.{timestamp}"
    
    with open(file_path, 'r', encoding='utf-8') as src:
        backup_content = src.read()
    
    with open(backup_path, 'w', encoding='utf-8') as dst:
        dst.write(backup_content)
    
    return backup_path


def confirm_action(message: str) -> bool:
    """Ask user for confirmation."""
    while True:
        response = input(f"\n{message} (yes/no): ").strip().lower()
        if response in ('yes', 'y'):
            return True
        elif response in ('no', 'n'):
            return False
        else:
            print("  Please enter 'yes' or 'no'")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Synchronize .env from .sample.env while preserving all existing values'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show changes without modifying files'
    )
    parser.add_argument(
        '--no-backup',
        action='store_true',
        help='Do not create backup before updating (not recommended)'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Skip confirmation prompts'
    )
    
    args = parser.parse_args()

    # Determine paths relative to script location
    script_dir = Path(__file__).parent
    repo_root = script_dir.parent
    sample_env_path = repo_root / '.sample.env'
    env_path = repo_root / '.env'

    # Validate files exist
    if not sample_env_path.exists():
        print(f"❌ Error: .sample.env not found at {sample_env_path}")
        sys.exit(1)

    if not env_path.exists():
        print(f"❌ Error: .env not found at {env_path}")
        print(f"   Please copy from .sample.env first: cp .sample.env .env (Linux/Mac) or copy .sample.env .env (Windows)")
        sys.exit(1)

    # Analyze differences
    print(f"\n📖 Analyzing .env files...")
    print(f"   Sample: {sample_env_path}")
    print(f"   Config: {env_path}")

    syncer = EnvSyncer(sample_env_path, env_path)
    syncer.analyze()

    # Show summary
    summary = syncer.get_summary()
    print(summary)

    # Determine if there are changes
    has_changes = bool(
        syncer.added_properties or 
        syncer.updated_properties or 
        syncer.removed_properties
    )

    if not has_changes and not syncer.commented_properties:
        print("✅ All done! Your .env is already synchronized.")
        return 0

    # Dry-run mode
    if args.dry_run:
        print("🏃 DRY-RUN MODE: No files were modified")
        print("   Run without --dry-run to apply these changes")
        return 0

    # Confirmation
    if not args.force:
        if not confirm_action("Apply these changes to .env?"):
            print("❌ Sync cancelled - no changes made")
            return 1

    # Create backup
    backup_path = None
    if not args.no_backup:
        print("\n💾 Creating backup...")
        backup_path = create_backup(env_path)
        print(f"   ✓ Backup created: {backup_path}")

    # Apply changes
    print("\n⚙️  Applying changes...")
    new_env_content = syncer.generate_new_env()

    with open(env_path, 'w', encoding='utf-8') as f:
        f.write(new_env_content)

    print(f"   ✓ Updated: {env_path}")

    # Success message
    print("\n" + "=" * 70)
    print("✅ SUCCESS! Your .env has been synchronized")
    print("=" * 70)

    if backup_path:
        print(f"\n📍 Backup location: {backup_path}")
        print("   Keep this file safe in case you need to revert changes")

    print("\n🚀 Next steps:")
    print("   1. Review the changes above")
    print("   2. Verify all values are correct")
    print("   3. Test the application: uv run app.py")

    return 0


if __name__ == '__main__':
    sys.exit(main())
