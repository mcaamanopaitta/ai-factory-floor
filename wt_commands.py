#!/usr/bin/env python3
"""
Worktree Management Commands
Command-line interface for advanced git worktree operations.
"""

import sys
import argparse
from pathlib import Path

# Add the current directory to sys.path to import devflow
sys.path.insert(0, str(Path(__file__).parent))

from devflow import WorktreeManager, console


def wt_merge_branch():
    """Command: wt-merge-branch <branch>"""
    parser = argparse.ArgumentParser(
        description="Merge a branch into its parent with automatic cleanup"
    )
    parser.add_argument("branch", help="Branch name to merge")
    parser.add_argument("--no-cleanup", action="store_true", 
                       help="Skip worktree and branch cleanup after merge")
    parser.add_argument("--no-push", action="store_true",
                       help="Skip pushing changes to remote")
    parser.add_argument("--preview", action="store_true",
                       help="Preview changes before merge")
    
    args = parser.parse_args()
    
    wt_manager = WorktreeManager()
    
    # Call merge_branch with enhanced options
    success = wt_manager.merge_branch(
        args.branch, 
        cleanup=not args.no_cleanup, 
        preview=args.preview,
        push=not args.no_push
    )
    
    sys.exit(0 if success else 1)


def wt_auto_clean():
    """Command: wt-auto-clean"""
    parser = argparse.ArgumentParser(
        description="Intelligently clean up merged branches and their worktrees"
    )
    parser.add_argument("--dry-run", action="store_true", default=True,
                       help="Preview what would be cleaned up (default)")
    parser.add_argument("--execute", action="store_true",
                       help="Actually perform the cleanup")
    
    args = parser.parse_args()
    
    if args.execute:
        dry_run = False
    else:
        dry_run = True
    
    wt_manager = WorktreeManager()
    candidates = wt_manager.auto_clean(dry_run=dry_run)
    
    if candidates:
        sys.exit(0)
    else:
        sys.exit(0)  # Success even if nothing to clean


def wt_ship_all():
    """Command: wt-ship-all"""
    parser = argparse.ArgumentParser(
        description="Ship (merge) multiple ready branches to their parents"
    )
    parser.add_argument("--dry-run", action="store_true", default=True,
                       help="Preview what would be shipped (default)")
    parser.add_argument("--execute", action="store_true",
                       help="Actually perform the shipping")
    
    args = parser.parse_args()
    
    if args.execute:
        dry_run = False
    else:
        dry_run = True
    
    wt_manager = WorktreeManager()
    candidates = wt_manager.ship_all(dry_run=dry_run)
    
    if candidates:
        sys.exit(0)
    else:
        sys.exit(0)  # Success even if nothing to ship


if __name__ == "__main__":
    # Determine which command was called based on sys.argv[0]
    script_name = Path(sys.argv[0]).name
    
    if script_name == "wt-merge-branch" or script_name == "wt_merge_branch.py":
        wt_merge_branch()
    elif script_name == "wt-auto-clean" or script_name == "wt_auto_clean.py":
        wt_auto_clean()
    elif script_name == "wt-ship-all" or script_name == "wt_ship_all.py":
        wt_ship_all()
    else:
        console.print("[red]Unknown command. This script should be called as:")
        console.print("  wt-merge-branch <branch>")
        console.print("  wt-auto-clean [--execute]")
        console.print("  wt-ship-all [--execute]")
        sys.exit(1)