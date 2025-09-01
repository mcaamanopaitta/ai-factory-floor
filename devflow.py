#!/usr/bin/env python3
"""
DevFlow TUI - AI Factory Floor Workflow Manager
A terminal UI for managing git worktrees, AI agents, and development workflows.
"""

import subprocess
import json
import os
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Tuple
import sys

# Rich for terminal UI
try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.layout import Layout
    from rich.live import Live
    from rich.text import Text
    from rich.tree import Tree
    from rich import print as rprint
    from rich.prompt import Prompt, Confirm
    RICH_AVAILABLE = True
except ImportError:
    # Fallback classes when rich is not available
    RICH_AVAILABLE = False
    class Console:
        def print(self, *args, **kwargs):
            # Strip rich markup for plain output
            if args:
                text = str(args[0])
                # Simple markup removal
                import re
                text = re.sub(r'\[.*?\]', '', text)
                print(text, *args[1:])
            else:
                print(*args, **kwargs)
    
    class Prompt:
        @staticmethod
        def ask(question, default=None):
            prompt = f"{question}"
            if default:
                prompt += f" [{default}]"
            prompt += ": "
            response = input(prompt).strip()
            return response if response else default
    
    class Confirm:
        @staticmethod
        def ask(question, default=True):
            default_text = "Y/n" if default else "y/N"
            response = input(f"{question} [{default_text}]: ").strip().lower()
            if not response:
                return default
            return response.startswith('y')
    
    # Fallback classes for other rich components
    class Table:
        def __init__(self, *args, **kwargs):
            self.rows = []
        def add_row(self, *args, **kwargs):
            self.rows.append(args)
        def add_column(self, *args, **kwargs):
            pass
    
    class Panel:
        def __init__(self, content, **kwargs):
            self.content = content
    
    class Layout:
        def __init__(self, *args, **kwargs):
            pass
    
    class Live:
        def __init__(self, *args, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def update(self, *args, **kwargs):
            pass
    
    class Text:
        def __init__(self, text, **kwargs):
            self.text = text
    
    class Tree:
        def __init__(self, label, **kwargs):
            self.label = label
        def add(self, *args, **kwargs):
            return Tree("sub")
    
    def rprint(*args, **kwargs):
        print(*args, **kwargs)

console = Console()


class WorktreeManager:
    """Manages git worktrees and their relationships"""
    
    def __init__(self):
        self.root_dir = Path.cwd()
        self.worktree_base = self.root_dir / "worktrees"
        self.context_dir = ".context"
        
    def get_worktrees(self) -> List[Dict]:
        """Get all worktrees with their metadata"""
        try:
            result = subprocess.run(
                ["git", "worktree", "list", "--porcelain"],
                capture_output=True,
                text=True,
                check=True
            )
            
            worktrees = []
            current_wt = {}
            
            for line in result.stdout.strip().split('\n'):
                if line.startswith('worktree '):
                    if current_wt:
                        worktrees.append(current_wt)
                    current_wt = {'path': line.split(' ', 1)[1]}
                elif line.startswith('HEAD '):
                    current_wt['head'] = line.split(' ', 1)[1]
                elif line.startswith('branch '):
                    current_wt['branch'] = line.split(' ', 1)[1].replace('refs/heads/', '')
                elif line.startswith('detached'):
                    current_wt['detached'] = True
                elif line == '':
                    if current_wt:
                        worktrees.append(current_wt)
                        current_wt = {}
            
            if current_wt:
                worktrees.append(current_wt)
                
            # Add additional metadata
            for wt in worktrees:
                path = Path(wt['path'])
                wt['name'] = path.name if path != self.root_dir else 'main'
                wt['is_current'] = path == Path.cwd()
                
                # Check for context
                context_path = path / self.context_dir
                if context_path.exists():
                    wt['has_context'] = True
                    # Try to find issue number
                    for f in context_path.glob('issue-*.md'):
                        wt['issue'] = f.stem.replace('issue-', '')
                        break
                else:
                    wt['has_context'] = False
                    
                # Check for nested worktrees
                wt['children'] = []
                if path != self.root_dir:
                    worktree_subdir = path / 'worktrees'
                    if worktree_subdir.exists():
                        for child in worktrees:
                            child_path = Path(child['path'])
                            if child_path.parent.parent == path:
                                wt['children'].append(child['name'])
                                
            return worktrees
            
        except subprocess.CalledProcessError as e:
            console.print(f"[red]Error getting worktrees: {e}[/red]")
            return []
    
    def create_worktree(self, branch_name: str, parent_branch: Optional[str] = None) -> bool:
        """Create a new worktree"""
        try:
            # Check if we're already in devenv shell
            if os.environ.get('DEVENV_ROOT'):
                # We're in devenv, call the script directly
                cmd = ["wt-new", branch_name]
                if parent_branch:
                    cmd.append(parent_branch)
            else:
                # Not in devenv, need to use devenv shell
                cmd = ["devenv", "shell", "--impure", "-c", f"wt-new {branch_name}"]
                if parent_branch:
                    cmd[-1] += f" {parent_branch}"
                
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                console.print(f"[green]✅ Created worktree: {branch_name}[/green]")
                return True
            else:
                console.print(f"[red]Failed to create worktree: {result.stderr}[/red]")
                return False
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            return False
    
    def merge_branch(self, branch_name: str, cleanup: bool = True, preview: bool = False, push: bool = True) -> bool:
        """Merge a branch into its parent with enhanced conflict resolution and cleanup"""
        try:
            # Find the worktree
            worktrees = self.get_worktrees()
            target_wt = None
            for wt in worktrees:
                if wt.get('branch') == branch_name or wt['name'] == branch_name:
                    target_wt = wt
                    break
            
            if not target_wt:
                console.print(f"[red]Branch {branch_name} not found in worktrees[/red]")
                return False
            
            # Determine parent branch
            parent_branch = self._get_parent_branch(target_wt)
            if not parent_branch:
                console.print(f"[red]Cannot determine parent branch for {branch_name}[/red]")
                return False
            
            # Show preview of changes if requested
            if preview:
                return self._preview_merge(branch_name, parent_branch)
            
            # Create backup before merge
            backup_ref = f"backup/{branch_name}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            subprocess.run(["git", "branch", backup_ref, parent_branch], capture_output=True)
            console.print(f"[cyan]📁 Created backup: {backup_ref}[/cyan]")
            
            console.print(f"[yellow]Merging {branch_name} into {parent_branch}...[/yellow]")
            
            # Switch to parent branch
            result = subprocess.run(["git", "checkout", parent_branch], capture_output=True, text=True)
            if result.returncode != 0:
                console.print(f"[red]Failed to checkout {parent_branch}: {result.stderr}[/red]")
                return False
            
            # Merge the branch
            result = subprocess.run(["git", "merge", branch_name, "--no-ff"], capture_output=True, text=True)
            
            if result.returncode != 0:
                if "CONFLICT" in result.stdout or "conflict" in result.stderr.lower():
                    return self._handle_merge_conflicts(branch_name, parent_branch, backup_ref)
                else:
                    console.print(f"[red]Merge failed: {result.stderr}[/red]")
                    self._rollback_merge(parent_branch, backup_ref)
                    return False
            
            console.print(f"[green]✅ Successfully merged {branch_name} into {parent_branch}[/green]")
            
            # Cleanup if requested
            if cleanup:
                self._cleanup_merged_branch(target_wt, branch_name)
            
            # Push changes if requested
            if push:
                push_result = subprocess.run(["git", "push"], capture_output=True, text=True)
                if push_result.returncode != 0:
                    console.print(f"[yellow]Warning: Failed to push changes: {push_result.stderr}[/yellow]")
                else:
                    console.print(f"[green]✅ Changes pushed to remote[/green]")
            else:
                console.print(f"[cyan]💾 Changes merged locally. Use 'git push' to push to remote[/cyan]")
            
            # Clean up backup on success
            subprocess.run(["git", "branch", "-D", backup_ref], capture_output=True)
                
            return True
            
        except Exception as e:
            console.print(f"[red]Error during merge: {e}[/red]")
            return False
    
    def _get_parent_branch(self, worktree: Dict) -> Optional[str]:
        """Determine parent branch for a worktree"""
        # Try git-town first
        try:
            result = subprocess.run(
                ["git", "config", f"git-town.branch.{worktree.get('branch', '')}.parent"],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except:
            pass
        
        # Fallback to main/master
        for candidate in ["main", "master"]:
            result = subprocess.run(["git", "show-ref", f"refs/heads/{candidate}"], capture_output=True)
            if result.returncode == 0:
                return candidate
        
        return None
    
    def _cleanup_merged_branch(self, worktree: Dict, branch_name: str):
        """Clean up worktree and branch after merge"""
        try:
            worktree_path = Path(worktree['path'])
            
            # Remove worktree
            result = subprocess.run(
                ["git", "worktree", "remove", str(worktree_path), "--force"],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                console.print(f"[green]✅ Removed worktree: {worktree_path.name}[/green]")
            else:
                console.print(f"[yellow]Warning: Could not remove worktree: {result.stderr}[/yellow]")
            
            # Delete branch
            result = subprocess.run(
                ["git", "branch", "-D", branch_name],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                console.print(f"[green]✅ Deleted branch: {branch_name}[/green]")
            else:
                console.print(f"[yellow]Warning: Could not delete branch: {result.stderr}[/yellow]")
                
        except Exception as e:
            console.print(f"[yellow]Warning during cleanup: {e}[/yellow]")
    
    def _preview_merge(self, branch_name: str, parent_branch: str) -> bool:
        """Show preview of what changes will be made during merge"""
        try:
            console.print(f"[cyan]📋 Merge Preview: {branch_name} → {parent_branch}[/cyan]")
            
            # Show commits that will be merged
            result = subprocess.run(
                ["git", "log", f"{parent_branch}..{branch_name}", "--oneline", "--graph"],
                capture_output=True, text=True
            )
            if result.returncode == 0 and result.stdout.strip():
                console.print("\n[yellow]📝 Commits to be merged:[/yellow]")
                console.print(result.stdout)
            else:
                console.print("[yellow]No commits to merge[/yellow]")
                return True
            
            # Show file changes
            result = subprocess.run(
                ["git", "diff", f"{parent_branch}...{branch_name}", "--name-status"],
                capture_output=True, text=True
            )
            if result.returncode == 0 and result.stdout.strip():
                console.print("\n[yellow]📁 Files that will be changed:[/yellow]")
                for line in result.stdout.strip().split('\n'):
                    if line:
                        status = line[0]
                        file_path = line[2:] if len(line) > 2 else line[1:]
                        color = {"A": "green", "M": "yellow", "D": "red"}.get(status, "white")
                        console.print(f"[{color}]{status}[/{color}] {file_path}")
            
            # Ask user if they want to proceed
            if not Confirm.ask("\n[cyan]Proceed with merge?[/cyan]", default=True):
                console.print("[yellow]Merge cancelled[/yellow]")
                return False
                
            return True
            
        except Exception as e:
            console.print(f"[red]Error showing preview: {e}[/red]")
            return False
    
    def _handle_merge_conflicts(self, branch_name: str, parent_branch: str, backup_ref: str) -> bool:
        """Handle merge conflicts with enhanced user guidance"""
        try:
            console.print(f"[red]⚠️  Merge conflicts detected![/red]")
            
            # Show conflicted files
            result = subprocess.run(["git", "diff", "--name-only", "--diff-filter=U"], capture_output=True, text=True)
            if result.returncode == 0 and result.stdout.strip():
                console.print("\n[yellow]📁 Files with conflicts:[/yellow]")
                for file_path in result.stdout.strip().split('\n'):
                    if file_path:
                        console.print(f"[red]⚔️[/red] {file_path}")
            
            console.print(f"\n[cyan]🛠️  Conflict Resolution Options:[/cyan]")
            console.print("[white]1.[/white] Open merge tool (if configured)")
            console.print("[white]2.[/white] Manual resolution with editor")
            console.print("[white]3.[/white] Abort merge and rollback")
            console.print("[white]4.[/white] Show conflict details")
            
            while True:
                choice = Prompt.ask(
                    "[cyan]Choose option[/cyan]",
                    choices=["1", "2", "3", "4"],
                    default="1"
                )
                
                if choice == "1":
                    # Try to open merge tool
                    result = subprocess.run(["git", "mergetool"], capture_output=False)
                    if result.returncode == 0:
                        if Confirm.ask("\n[green]Conflicts resolved? Ready to commit?[/green]"):
                            subprocess.run(["git", "commit", "--no-edit"], check=True)
                            console.print(f"[green]✅ Merge completed successfully![/green]")
                            return True
                    else:
                        console.print("[yellow]Merge tool not configured or failed[/yellow]")
                        
                elif choice == "2":
                    console.print("\n[yellow]📝 Manual Resolution Steps:[/yellow]")
                    console.print("1. Edit conflicted files to resolve conflicts")
                    console.print("2. Remove conflict markers (<<<<<<, ======, >>>>>>)")
                    console.print("3. git add <resolved-files>")
                    console.print("4. git commit")
                    console.print(f"5. Re-run: wt-merge-branch {branch_name}")
                    
                    if Confirm.ask("\n[cyan]Open shell for manual resolution?[/cyan]"):
                        console.print("[yellow]Opening shell. Exit when conflicts are resolved.[/yellow]")
                        os.system(os.environ.get('SHELL', '/bin/bash'))
                        
                        if Confirm.ask("[green]Conflicts resolved and committed?[/green]"):
                            # Check if merge is complete
                            result = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
                            if "UU" not in result.stdout:
                                console.print(f"[green]✅ Merge completed successfully![/green]")
                                return True
                            else:
                                console.print("[yellow]Conflicts still exist. Please resolve them.[/yellow]")
                                continue
                    
                elif choice == "3":
                    # Abort merge
                    subprocess.run(["git", "merge", "--abort"], capture_output=True)
                    self._rollback_merge(parent_branch, backup_ref)
                    return False
                    
                elif choice == "4":
                    # Show conflict details
                    result = subprocess.run(["git", "diff"], capture_output=True, text=True)
                    if result.stdout:
                        console.print("\n[yellow]📋 Conflict Details:[/yellow]")
                        console.print(result.stdout[:2000])  # Limit output
                        if len(result.stdout) > 2000:
                            console.print("[dim]... (output truncated)[/dim]")
                    continue
                    
                break
                
            return False
            
        except Exception as e:
            console.print(f"[red]Error handling conflicts: {e}[/red]")
            self._rollback_merge(parent_branch, backup_ref)
            return False
    
    def _rollback_merge(self, parent_branch: str, backup_ref: str) -> None:
        """Rollback a failed merge using the backup"""
        try:
            console.print(f"[yellow]🔄 Rolling back merge...[/yellow]")
            
            # Reset to backup
            subprocess.run(["git", "reset", "--hard", backup_ref], capture_output=True)
            console.print(f"[green]✅ Rollback complete. Restored to {backup_ref}[/green]")
            
            # Clean up backup
            subprocess.run(["git", "branch", "-D", backup_ref], capture_output=True)
            
        except Exception as e:
            console.print(f"[red]Error during rollback: {e}[/red]")
            console.print(f"[yellow]Manual rollback: git reset --hard {backup_ref}[/yellow]")
    
    def auto_clean(self, dry_run: bool = True) -> List[str]:
        """Intelligently clean up merged branches"""
        try:
            console.print("[yellow]Scanning for merged branches...[/yellow]")
            
            # Get merged branches
            result = subprocess.run(
                ["git", "branch", "--merged"],
                capture_output=True, text=True
            )
            
            if result.returncode != 0:
                console.print(f"[red]Failed to get merged branches: {result.stderr}[/red]")
                return []
            
            merged_branches = [
                line.strip().replace('*', '').strip() 
                for line in result.stdout.strip().split('\n')
                if line.strip() and not line.strip().replace('*', '').strip() in ['main', 'master']
            ]
            
            if not merged_branches:
                console.print("[green]No merged branches found for cleanup[/green]")
                return []
            
            # Get worktrees for these branches
            worktrees = self.get_worktrees()
            cleanup_candidates = []
            
            for branch in merged_branches:
                for wt in worktrees:
                    if wt.get('branch') == branch:
                        cleanup_candidates.append({
                            'branch': branch,
                            'worktree': wt,
                            'path': Path(wt['path'])
                        })
            
            if not cleanup_candidates:
                console.print("[green]No worktrees found for merged branches[/green]")
                return []
            
            if dry_run:
                console.print(f"[cyan]Would clean up {len(cleanup_candidates)} items:[/cyan]")
                for candidate in cleanup_candidates:
                    console.print(f"  - Branch: {candidate['branch']}, Worktree: {candidate['path'].name}")
                return [c['branch'] for c in cleanup_candidates]
            
            # Confirm cleanup
            if not Confirm.ask(f"Clean up {len(cleanup_candidates)} merged branches and their worktrees?"):
                console.print("[yellow]Cleanup cancelled[/yellow]")
                return []
            
            cleaned = []
            for candidate in cleanup_candidates:
                try:
                    self._cleanup_merged_branch(candidate['worktree'], candidate['branch'])
                    cleaned.append(candidate['branch'])
                except Exception as e:
                    console.print(f"[red]Failed to clean up {candidate['branch']}: {e}[/red]")
            
            console.print(f"[green]✅ Cleaned up {len(cleaned)} branches[/green]")
            return cleaned
            
        except Exception as e:
            console.print(f"[red]Error during auto-clean: {e}[/red]")
            return []
    
    def ship_all(self, dry_run: bool = True) -> List[str]:
        """Ship multiple ready branches"""
        try:
            console.print("[yellow]Scanning for ready branches...[/yellow]")
            
            worktrees = self.get_worktrees()
            
            # Find feature branches that might be ready
            ready_candidates = []
            for wt in worktrees:
                branch = wt.get('branch', '')
                if branch and branch not in ['main', 'master'] and not wt.get('detached'):
                    # Check if branch has commits ahead
                    parent = self._get_parent_branch(wt)
                    if parent:
                        result = subprocess.run(
                            ["git", "rev-list", "--count", f"{parent}..{branch}"],
                            capture_output=True, text=True
                        )
                        if result.returncode == 0 and int(result.stdout.strip()) > 0:
                            ready_candidates.append({
                                'branch': branch,
                                'worktree': wt,
                                'parent': parent,
                                'commits_ahead': int(result.stdout.strip())
                            })
            
            if not ready_candidates:
                console.print("[green]No ready branches found for shipping[/green]")
                return []
            
            if dry_run:
                console.print(f"[cyan]Would ship {len(ready_candidates)} branches:[/cyan]")
                for candidate in ready_candidates:
                    console.print(f"  - {candidate['branch']} → {candidate['parent']} ({candidate['commits_ahead']} commits)")
                return [c['branch'] for c in ready_candidates]
            
            # Show preview and confirm
            console.print(f"[cyan]Ready to ship {len(ready_candidates)} branches:[/cyan]")
            for candidate in ready_candidates:
                console.print(f"  - {candidate['branch']} → {candidate['parent']} ({candidate['commits_ahead']} commits)")
            
            if not Confirm.ask(f"Ship all {len(ready_candidates)} branches?"):
                console.print("[yellow]Shipping cancelled[/yellow]")
                return []
            
            shipped = []
            for candidate in ready_candidates:
                console.print(f"[yellow]Shipping {candidate['branch']}...[/yellow]")
                if self.merge_branch(candidate['branch'], cleanup=True):
                    shipped.append(candidate['branch'])
                else:
                    console.print(f"[red]Failed to ship {candidate['branch']}[/red]")
            
            console.print(f"[green]✅ Shipped {len(shipped)} branches[/green]")
            return shipped
            
        except Exception as e:
            console.print(f"[red]Error during ship-all: {e}[/red]")
            return []


class MCPServerManager:
    """Manages MCP (Model Context Protocol) servers"""
    
    def __init__(self):
        self.mcp_dir = Path(".mcp")
        self.servers = {
            "context7": "Context7 (Documentation)",
            "playwright": "Playwright (Browser)",
            "python": "Python Sandbox",
            "sequential": "Sequential Thinking",
            "zen": "Zen Multi-Model"
        }
        
    def get_status(self) -> Dict[str, str]:
        """Get status of all MCP servers"""
        status = {}
        pid_dir = self.mcp_dir / "pids"
        
        if not pid_dir.exists():
            return {name: "not configured" for name in self.servers}
            
        for server_name in self.servers:
            pid_file = pid_dir / f"{server_name}.pid"
            if pid_file.exists():
                try:
                    pid = int(pid_file.read_text().strip())
                    # Check if process is running
                    os.kill(pid, 0)
                    status[server_name] = "running"
                except (OSError, ValueError):
                    status[server_name] = "stopped"
            else:
                status[server_name] = "not started"
                
        return status
    
    def start_servers(self):
        """Start all MCP servers"""
        if os.environ.get('DEVENV_ROOT'):
            subprocess.run(["mcp-start"])
        else:
            subprocess.run(["devenv", "shell", "--impure", "-c", "mcp-start"])
        
    def stop_servers(self):
        """Stop all MCP servers"""
        if os.environ.get('DEVENV_ROOT'):
            subprocess.run(["mcp-stop"])
        else:
            subprocess.run(["devenv", "shell", "--impure", "-c", "mcp-stop"])


class DevFlowTUI:
    """Main TUI application"""
    
    def __init__(self):
        self.wt_manager = WorktreeManager()
        self.mcp_manager = MCPServerManager()
        self.running = True
        
    def create_worktree_tree(self) -> Tree:
        """Create a tree visualization of worktrees"""
        tree = Tree("🌳 [bold]Worktrees[/bold]")
        worktrees = self.wt_manager.get_worktrees()
        
        # Build tree structure
        root_wts = [wt for wt in worktrees if Path(wt['path']).parent == self.wt_manager.root_dir.parent or Path(wt['path']) == self.wt_manager.root_dir]
        
        for wt in root_wts:
            branch_name = wt.get('branch', 'detached')
            issue = f" #{wt['issue']}" if wt.get('issue') else ""
            current = " [cyan][current][/cyan]" if wt['is_current'] else ""
            
            node_text = f"{branch_name}{issue}{current}"
            node = tree.add(node_text)
            
            # Add children recursively
            self._add_children_to_tree(node, wt, worktrees)
            
        return tree
    
    def _add_children_to_tree(self, parent_node, parent_wt, all_worktrees):
        """Recursively add children to tree"""
        for child_name in parent_wt.get('children', []):
            child_wt = next((wt for wt in all_worktrees if wt['name'] == child_name), None)
            if child_wt:
                branch_name = child_wt.get('branch', 'detached')
                issue = f" #{child_wt['issue']}" if child_wt.get('issue') else ""
                current = " [cyan][current][/cyan]" if child_wt['is_current'] else ""
                
                node_text = f"{branch_name}{issue}{current}"
                child_node = parent_node.add(node_text)
                
                # Recurse for nested children
                self._add_children_to_tree(child_node, child_wt, all_worktrees)
    
    def create_mcp_status_table(self) -> Table:
        """Create a table showing MCP server status"""
        table = Table(title="🔌 MCP Server Status", show_header=True)
        table.add_column("Server", style="cyan")
        table.add_column("Status", style="green")
        
        status = self.mcp_manager.get_status()
        for server_name, desc in self.mcp_manager.servers.items():
            server_status = status.get(server_name, "unknown")
            status_style = "green" if server_status == "running" else "red" if server_status == "stopped" else "yellow"
            table.add_row(desc, f"[{status_style}]{server_status}[/{status_style}]")
            
        return table
    
    def create_layout(self) -> Layout:
        """Create the main layout"""
        layout = Layout()
        
        # Split into header and body
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body"),
            Layout(name="footer", size=3)
        )
        
        # Header
        layout["header"].update(
            Panel(
                "[bold blue]🏭 AI Factory Floor - DevFlow Manager[/bold blue]\n"
                "[dim]Manage worktrees, AI agents, and development workflows[/dim]",
                border_style="blue"
            )
        )
        
        # Body - split into left and right
        layout["body"].split_row(
            Layout(name="left"),
            Layout(name="right")
        )
        
        # Left panel - worktree tree
        layout["body"]["left"].update(
            Panel(self.create_worktree_tree(), border_style="green")
        )
        
        # Right panel - MCP status
        layout["body"]["right"].update(
            Panel(self.create_mcp_status_table(), border_style="yellow")
        )
        
        # Footer - commands
        layout["footer"].update(
            Panel(
                "[bold]Commands:[/bold] "
                "[cyan](n)[/cyan]ew worktree | "
                "[cyan](a)[/cyan]gent start | "
                "[cyan](m)[/cyan]erge branch | "
                "[cyan](c)[/cyan]lean auto | "
                "[cyan](S)[/cyan]hip all | "
                "[cyan](s)[/cyan]tart MCP | "
                "[cyan](k)[/cyan]ill MCP | "
                "[cyan](r)[/cyan]efresh | "
                "[cyan](q)[/cyan]uit",
                border_style="dim"
            )
        )
        
        return layout
    
    def handle_input(self) -> bool:
        """Handle user input"""
        key = Prompt.ask(
            "\n[bold]Command[/bold]",
            choices=["n", "a", "m", "c", "S", "s", "k", "r", "q"],
            default="r"
        )
        
        if key == "q":
            return False
        elif key == "n":
            branch = Prompt.ask("[bold]Branch name[/bold]")
            parent = Prompt.ask("[bold]Parent branch (optional)[/bold]", default="")
            self.wt_manager.create_worktree(branch, parent if parent else None)
        elif key == "a":
            # Start agent in worktree
            worktree = Prompt.ask("[bold]Worktree name (or 'here' for current)[/bold]")
            if worktree == "here":
                # Start agent in current directory
                if os.environ.get('DEVENV_ROOT'):
                    subprocess.run(["agent-here"])
                else:
                    subprocess.run(["devenv", "shell", "--impure", "-c", "agent-here"])
            else:
                # Start agent in specific worktree
                worktree_path = Path("worktrees") / worktree
                if worktree_path.exists():
                    # If in zellij, switch to worktree and start agent
                    if os.environ.get('ZELLIJ'):
                        # Create a new tab for the agent
                        subprocess.run(["zellij", "action", "new-tab", "--name", f"agent-{worktree}", "--cwd", str(worktree_path)])
                        # Run agent-here in the new tab
                        subprocess.run(["zellij", "action", "write-chars", "agent-here\n"])
                    else:
                        # Not in zellij, run in current terminal
                        if os.environ.get('DEVENV_ROOT'):
                            subprocess.run(["sh", "-c", f"cd {worktree_path} && agent-here"])
                        else:
                            subprocess.run(["devenv", "shell", "--impure", "-c", f"cd {worktree_path} && agent-here"])
                else:
                    console.print(f"[red]Worktree {worktree} not found[/red]")
        elif key == "s":
            console.print("[yellow]Starting MCP servers...[/yellow]")
            self.mcp_manager.start_servers()
        elif key == "m":
            # Merge branch
            branch = Prompt.ask("[bold]Branch name to merge[/bold]")
            cleanup = Confirm.ask("Clean up worktree after merge?", default=True)
            self.wt_manager.merge_branch(branch, cleanup=cleanup)
        elif key == "c":
            # Auto clean
            dry_run = Confirm.ask("Dry run first (preview only)?", default=True)
            candidates = self.wt_manager.auto_clean(dry_run=dry_run)
            if candidates and dry_run:
                if Confirm.ask("Proceed with cleanup?"):
                    self.wt_manager.auto_clean(dry_run=False)
        elif key == "S":
            # Ship all
            dry_run = Confirm.ask("Dry run first (preview only)?", default=True)
            candidates = self.wt_manager.ship_all(dry_run=dry_run)
            if candidates and dry_run:
                if Confirm.ask("Proceed with shipping all?"):
                    self.wt_manager.ship_all(dry_run=False)
        elif key == "k":
            console.print("[yellow]Stopping MCP servers...[/yellow]")
            self.mcp_manager.stop_servers()
        elif key == "r":
            console.print("[dim]Refreshing...[/dim]")
            
        return True
    
    def run(self):
        """Run the TUI"""
        console.clear()
        
        while self.running:
            layout = self.create_layout()
            console.print(layout)
            
            if not self.handle_input():
                self.running = False
                
            console.clear()
        
        console.print("[green]Goodbye! 👋[/green]")


def main():
    """Main entry point"""
    app = DevFlowTUI()
    
    try:
        app.run()
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
    except Exception as e:
        console.print(f"\n[red]Error: {e}[/red]")
        raise


if __name__ == "__main__":
    main()