"""
PR Enricher
Enriches existing PR JSON files with file change data from GitHub API
"""

import json
from pathlib import Path
from typing import List, Dict
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from .github_api import GitHubClient
from .local_loader import LocalPRLoader


console = Console()


class PREnricher:
    """Enrich PR data with file information"""

    def __init__(self, github_client: GitHubClient):
        self.client = github_client

    def enrich_pr_file(self, pr_file_path: Path, owner: str, repo: str) -> bool:
        """
        Enrich a single PR JSON file with file data

        Args:
            pr_file_path: Path to PR JSON file
            owner: Repository owner
            repo: Repository name

        Returns:
            True if enriched successfully, False otherwise
        """
        try:
            # Read existing PR data
            with open(pr_file_path, 'r', encoding='utf-8') as f:
                pr_data = json.load(f)

            # Skip if already has files
            if 'files' in pr_data and pr_data['files']:
                console.print(f"[dim]  PR #{pr_data['number']} already has files data, skipping[/dim]")
                return True

            pr_number = pr_data.get('number')
            if not pr_number:
                console.print(f"[yellow]  ⚠️  No PR number in {pr_file_path.name}[/yellow]")
                return False

            # Fetch files from GitHub API
            files = self.client.get_pr_files(owner, repo, pr_number)

            # Simplify file data (keep only essential fields + patch for analysis)
            simplified_files = []
            for file in files:
                simplified = {
                    'filename': file.get('filename'),
                    'status': file.get('status'),
                    'additions': file.get('additions', 0),
                    'deletions': file.get('deletions', 0),
                    'changes': file.get('changes', 0)
                }

                # Include patch for small files (< 500 changes) to improve AI analysis
                # Skip binary files and very large diffs
                patch = file.get('patch')
                changes = file.get('changes', 0)

                if patch and changes < 500:
                    # Limit patch size to 1500 chars to keep JSON compact
                    simplified['patch'] = patch[:1500]

                simplified_files.append(simplified)

            # Add files to PR data
            pr_data['files'] = simplified_files
            pr_data['files_count'] = len(simplified_files)

            # Save updated PR data
            with open(pr_file_path, 'w', encoding='utf-8') as f:
                json.dump(pr_data, f, indent=2, ensure_ascii=False)

            return True

        except Exception as e:
            console.print(f"[red]  ❌ Error enriching {pr_file_path.name}: {e}[/red]")
            return False

    def enrich_directory(self, directory: Path, owner: str, repo: str, recursive: bool = False) -> Dict:
        """
        Enrich all PR files in directory

        Args:
            directory: Directory containing PR JSON files
            owner: Repository owner
            repo: Repository name (if None, extracts from path)
            recursive: Search subdirectories

        Returns:
            Statistics dictionary
        """
        loader = LocalPRLoader(directory)

        # Find all PR files
        if recursive:
            pattern = "**/*.json"
        else:
            pattern = "*.json"

        pr_files = list(directory.glob(pattern))
        pr_files = [f for f in pr_files if f.name.startswith("pr_")]

        if not pr_files:
            console.print(f"[yellow]⚠️  No PR files found in {directory}[/yellow]")
            return {"total": 0, "enriched": 0, "skipped": 0, "failed": 0}

        stats = {
            "total": len(pr_files),
            "enriched": 0,
            "skipped": 0,
            "failed": 0
        }

        console.print(f"\n[cyan]📂 Found {len(pr_files)} PR files[/cyan]")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console
        ) as progress:
            task = progress.add_task(
                "[cyan]Enriching PRs...",
                total=len(pr_files)
            )

            for pr_file in pr_files:
                # Try to extract repo from path if not provided
                current_repo = repo
                if not current_repo:
                    # Assume structure: .../org/repo/pr_123.json
                    if len(pr_file.parts) >= 2:
                        current_repo = pr_file.parts[-2]

                if not current_repo:
                    console.print(f"[yellow]⚠️  Cannot determine repo for {pr_file.name}[/yellow]")
                    stats["failed"] += 1
                    progress.update(task, advance=1)
                    continue

                # Read PR to get number for progress
                try:
                    with open(pr_file, 'r', encoding='utf-8') as f:
                        pr_data = json.load(f)
                    pr_number = pr_data.get('number', '?')

                    # Check if already enriched
                    if 'files' in pr_data and pr_data['files']:
                        stats["skipped"] += 1
                        progress.update(
                            task,
                            advance=1,
                            description=f"[dim]PR #{pr_number} (already enriched)[/dim]"
                        )
                        continue

                except Exception:
                    pr_number = '?'

                progress.update(
                    task,
                    description=f"[cyan]Enriching PR #{pr_number}..."
                )

                success = self.enrich_pr_file(pr_file, owner, current_repo)

                if success:
                    stats["enriched"] += 1
                else:
                    stats["failed"] += 1

                progress.update(task, advance=1)

        return stats

    def enrich_organization(self, org_path: Path, owner: str) -> Dict:
        """
        Enrich all repositories in organization directory

        Args:
            org_path: Path to organization directory
            owner: Organization name

        Returns:
            Combined statistics
        """
        if not org_path.exists() or not org_path.is_dir():
            console.print(f"[red]❌ Organization directory not found: {org_path}[/red]")
            return {}

        # Find all repository directories
        repo_dirs = [d for d in org_path.iterdir() if d.is_dir()]

        if not repo_dirs:
            console.print(f"[yellow]⚠️  No repository directories found in {org_path}[/yellow]")
            return {}

        console.print(f"\n[cyan]📊 Found {len(repo_dirs)} repositories[/cyan]")

        total_stats = {
            "repositories": len(repo_dirs),
            "total": 0,
            "enriched": 0,
            "skipped": 0,
            "failed": 0
        }

        for repo_dir in repo_dirs:
            repo_name = repo_dir.name
            console.print(f"\n[bold cyan]Repository: {repo_name}[/bold cyan]")

            stats = self.enrich_directory(repo_dir, owner, repo_name, recursive=False)

            # Aggregate stats
            total_stats["total"] += stats.get("total", 0)
            total_stats["enriched"] += stats.get("enriched", 0)
            total_stats["skipped"] += stats.get("skipped", 0)
            total_stats["failed"] += stats.get("failed", 0)

        return total_stats