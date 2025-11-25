"""
Exporters for saving pull request data in various formats
"""

import json
import csv
from pathlib import Path
from typing import List, Dict
from datetime import datetime
from rich.console import Console


console = Console()


class PRExporter:
    """Base class for exporting pull request data"""

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _create_repo_dir(self, org_name: str, repo_name: str) -> Path:
        """Create directory for organization and repository"""
        repo_dir = self.output_dir / org_name / repo_name
        repo_dir.mkdir(parents=True, exist_ok=True)
        return repo_dir


class JSONExporter(PRExporter):
    """Export pull requests to JSON format"""

    def export(self, prs: List[Dict], org_name: str, repo_name: str):
        """
        Export PRs to JSON files

        Creates:
        - Individual JSON file for each PR
        - summary.json with metadata
        """
        repo_dir = self._create_repo_dir(org_name, repo_name)

        console.print(f"\n[cyan]💾 Saving {len(prs)} PRs to {repo_dir}/[/cyan]")

        # Save individual PR files
        for pr in prs:
            pr_number = pr['number']
            filename = f"pr_{pr_number}.json"
            filepath = repo_dir / filename

            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(pr, f, indent=2, ensure_ascii=False)

        # Create summary
        summary = {
            "organization": org_name,
            "repository": repo_name,
            "total_prs": len(prs),
            "exported_at": datetime.now().isoformat(),
            "pr_numbers": [pr['number'] for pr in prs],
            "statistics": self._calculate_statistics(prs)
        }

        summary_path = repo_dir / "summary.json"
        with open(summary_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)

        console.print(f"[green]✅ Saved {len(prs)} PRs to {repo_dir}/[/green]")

    def export_multiple(self, repo_prs: Dict[str, List[Dict]], org_name: str):
        """Export PRs from multiple repositories"""
        total_prs = sum(len(prs) for prs in repo_prs.values())
        console.print(f"\n[cyan]💾 Saving {total_prs} PRs from {len(repo_prs)} repositories...[/cyan]")

        for repo_name, prs in repo_prs.items():
            if prs:
                self.export(prs, org_name, repo_name)

        console.print(f"[green]✅ Export complete! Saved to {self.output_dir}/{org_name}/[/green]")

    def _calculate_statistics(self, prs: List[Dict]) -> Dict:
        """Calculate statistics from PRs"""
        if not prs:
            return {}

        states = {"open": 0, "closed": 0, "merged": 0}
        for pr in prs:
            if pr.get('state') == 'open':
                states['open'] += 1
            elif pr.get('pull_request', {}).get('merged_at'):
                states['merged'] += 1
            else:
                states['closed'] += 1

        return {
            "by_state": states,
            "oldest": prs[-1]['created_at'] if prs else None,
            "newest": prs[0]['created_at'] if prs else None
        }


class CSVExporter(PRExporter):
    """Export pull requests to CSV format"""

    def export(self, prs: List[Dict], org_name: str, repo_name: str):
        """Export PRs to CSV file"""
        repo_dir = self._create_repo_dir(org_name, repo_name)
        csv_path = repo_dir / "pull_requests.csv"

        console.print(f"\n[cyan]💾 Saving {len(prs)} PRs to {csv_path}[/cyan]")

        # Define CSV columns
        fieldnames = [
            'number',
            'title',
            'state',
            'is_merged',
            'author',
            'created_at',
            'updated_at',
            'closed_at',
            'merged_at',
            'url',
            'labels',
            'comments',
            'additions',
            'deletions'
        ]

        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for pr in prs:
                row = {
                    'number': pr.get('number'),
                    'title': pr.get('title'),
                    'state': pr.get('state'),
                    'is_merged': 'Yes' if pr.get('pull_request', {}).get('merged_at') else 'No',
                    'author': pr.get('user', {}).get('login'),
                    'created_at': pr.get('created_at'),
                    'updated_at': pr.get('updated_at'),
                    'closed_at': pr.get('closed_at', ''),
                    'merged_at': pr.get('pull_request', {}).get('merged_at', ''),
                    'url': pr.get('html_url'),
                    'labels': ', '.join([label.get('name', '') for label in pr.get('labels', [])]),
                    'comments': pr.get('comments', 0),
                    'additions': pr.get('additions', 0),
                    'deletions': pr.get('deletions', 0)
                }
                writer.writerow(row)

        console.print(f"[green]✅ Saved CSV to {csv_path}[/green]")

    def export_multiple(self, repo_prs: Dict[str, List[Dict]], org_name: str):
        """Export PRs from multiple repositories"""
        total_prs = sum(len(prs) for prs in repo_prs.values())
        console.print(f"\n[cyan]💾 Saving {total_prs} PRs to CSV files...[/cyan]")

        for repo_name, prs in repo_prs.items():
            if prs:
                self.export(prs, org_name, repo_name)

        # Create combined CSV
        combined_path = self.output_dir / org_name / "all_pull_requests.csv"
        console.print(f"\n[cyan]💾 Creating combined CSV at {combined_path}[/cyan]")

        fieldnames = [
            'repository',
            'number',
            'title',
            'state',
            'is_merged',
            'author',
            'created_at',
            'updated_at',
            'closed_at',
            'merged_at',
            'url',
            'labels',
            'comments'
        ]

        with open(combined_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for repo_name, prs in repo_prs.items():
                for pr in prs:
                    row = {
                        'repository': repo_name,
                        'number': pr.get('number'),
                        'title': pr.get('title'),
                        'state': pr.get('state'),
                        'is_merged': 'Yes' if pr.get('pull_request', {}).get('merged_at') else 'No',
                        'author': pr.get('user', {}).get('login'),
                        'created_at': pr.get('created_at'),
                        'updated_at': pr.get('updated_at'),
                        'closed_at': pr.get('closed_at', ''),
                        'merged_at': pr.get('pull_request', {}).get('merged_at', ''),
                        'url': pr.get('html_url'),
                        'labels': ', '.join([label.get('name', '') for label in pr.get('labels', [])]),
                        'comments': pr.get('comments', 0)
                    }
                    writer.writerow(row)

        console.print(f"[green]✅ Export complete! Saved to {self.output_dir}/{org_name}/[/green]")


class MarkdownExporter(PRExporter):
    """Export pull requests to Markdown format"""

    def export(self, prs: List[Dict], org_name: str, repo_name: str):
        """Export PRs to Markdown file"""
        repo_dir = self._create_repo_dir(org_name, repo_name)
        md_path = repo_dir / "pull_requests.md"

        console.print(f"\n[cyan]💾 Saving {len(prs)} PRs to {md_path}[/cyan]")

        with open(md_path, 'w', encoding='utf-8') as f:
            # Header
            f.write(f"# Pull Requests - {org_name}/{repo_name}\n\n")
            f.write(f"**Total PRs:** {len(prs)}\n\n")
            f.write(f"**Exported:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

            # Statistics
            stats = self._calculate_statistics(prs)
            if stats:
                f.write("## Statistics\n\n")
                f.write(f"- Open: {stats['by_state']['open']}\n")
                f.write(f"- Merged: {stats['by_state']['merged']}\n")
                f.write(f"- Closed: {stats['by_state']['closed']}\n\n")

            # PR list
            f.write("## Pull Requests\n\n")

            for pr in prs:
                # Determine status emoji
                if pr.get('state') == 'open':
                    status = "🟢 Open"
                elif pr.get('pull_request', {}).get('merged_at'):
                    status = "🟣 Merged"
                else:
                    status = "🔴 Closed"

                f.write(f"### #{pr['number']} - {pr['title']}\n\n")
                f.write(f"**Status:** {status}\n\n")
                f.write(f"**Author:** @{pr.get('user', {}).get('login', 'unknown')}\n\n")
                f.write(f"**Created:** {pr.get('created_at', 'N/A')}\n\n")

                if pr.get('closed_at'):
                    f.write(f"**Closed:** {pr['closed_at']}\n\n")

                if pr.get('pull_request', {}).get('merged_at'):
                    f.write(f"**Merged:** {pr['pull_request']['merged_at']}\n\n")

                # Labels
                labels = pr.get('labels', [])
                if labels:
                    label_names = [f"`{label.get('name')}`" for label in labels]
                    f.write(f"**Labels:** {', '.join(label_names)}\n\n")

                # URL
                f.write(f"**URL:** [{pr['html_url']}]({pr['html_url']})\n\n")

                # Body preview
                body = pr.get('body', '')
                if body:
                    preview = body[:200] + "..." if len(body) > 200 else body
                    f.write(f"**Description:**\n```\n{preview}\n```\n\n")

                f.write("---\n\n")

        console.print(f"[green]✅ Saved Markdown to {md_path}[/green]")

    def export_multiple(self, repo_prs: Dict[str, List[Dict]], org_name: str):
        """Export PRs from multiple repositories"""
        total_prs = sum(len(prs) for prs in repo_prs.values())
        console.print(f"\n[cyan]💾 Saving {total_prs} PRs to Markdown files...[/cyan]")

        for repo_name, prs in repo_prs.items():
            if prs:
                self.export(prs, org_name, repo_name)

        # Create index file
        index_path = self.output_dir / org_name / "README.md"
        with open(index_path, 'w', encoding='utf-8') as f:
            f.write(f"# Pull Requests Report - {org_name}\n\n")
            f.write(f"**Exported:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write(f"**Total Repositories:** {len(repo_prs)}\n\n")
            f.write(f"**Total PRs:** {total_prs}\n\n")

            f.write("## Repositories\n\n")
            for repo_name, prs in repo_prs.items():
                stats = self._calculate_statistics(prs)
                f.write(f"### {repo_name}\n\n")
                f.write(f"- Total PRs: {len(prs)}\n")
                if stats:
                    f.write(f"- Open: {stats['by_state']['open']}\n")
                    f.write(f"- Merged: {stats['by_state']['merged']}\n")
                    f.write(f"- Closed: {stats['by_state']['closed']}\n")
                f.write(f"- [View Details]({repo_name}/pull_requests.md)\n\n")

        console.print(f"[green]✅ Export complete! Saved to {self.output_dir}/{org_name}/[/green]")

    def _calculate_statistics(self, prs: List[Dict]) -> Dict:
        """Calculate statistics from PRs"""
        if not prs:
            return {}

        states = {"open": 0, "closed": 0, "merged": 0}
        for pr in prs:
            if pr.get('state') == 'open':
                states['open'] += 1
            elif pr.get('pull_request', {}).get('merged_at'):
                states['merged'] += 1
            else:
                states['closed'] += 1

        return {"by_state": states}