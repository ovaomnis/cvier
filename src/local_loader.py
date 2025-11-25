"""
Local PR data loader
Loads pull request data from locally saved JSON files
"""

import json
from pathlib import Path
from typing import List, Dict, Optional
from rich.console import Console


console = Console()


class LocalPRLoader:
    """Load PR data from local JSON files"""

    def __init__(self, base_path: Path):
        self.base_path = Path(base_path)

    def load_prs_from_directory(self, recursive: bool = False) -> List[Dict]:
        """
        Load all PRs from directory

        Args:
            recursive: If True, search subdirectories recursively

        Returns:
            List of PR dictionaries
        """
        prs = []

        if recursive:
            # Search all subdirectories
            pattern = "**/*.json"
        else:
            # Search only in current directory
            pattern = "*.json"

        json_files = list(self.base_path.glob(pattern))

        # Filter out summary.json files
        pr_files = [f for f in json_files if f.name.startswith("pr_")]

        console.print(f"[cyan]Found {len(pr_files)} PR files in {self.base_path}[/cyan]")

        for pr_file in pr_files:
            try:
                with open(pr_file, 'r', encoding='utf-8') as f:
                    pr_data = json.load(f)
                    prs.append(pr_data)
            except Exception as e:
                console.print(f"[yellow]⚠️  Error loading {pr_file.name}: {e}[/yellow]")

        # Sort by created date (newest first)
        prs.sort(key=lambda x: x.get('created_at', ''), reverse=True)

        return prs

    def load_prs_from_repos(self, org_name: str, repo_names: Optional[List[str]] = None) -> Dict[str, List[Dict]]:
        """
        Load PRs from multiple repositories

        Args:
            org_name: Organization name
            repo_names: List of repository names (if None, loads all repos)

        Returns:
            Dictionary mapping repo name to list of PRs
        """
        org_path = self.base_path / org_name

        if not org_path.exists():
            console.print(f"[red]❌ Organization directory not found: {org_path}[/red]")
            return {}

        results = {}

        # Get all repository directories
        if repo_names:
            repo_dirs = [org_path / repo for repo in repo_names if (org_path / repo).exists()]
        else:
            repo_dirs = [d for d in org_path.iterdir() if d.is_dir()]

        for repo_dir in repo_dirs:
            repo_name = repo_dir.name
            loader = LocalPRLoader(repo_dir)
            prs = loader.load_prs_from_directory(recursive=False)
            results[repo_name] = prs

        return results

    def get_statistics(self, prs: List[Dict]) -> Dict:
        """
        Calculate statistics from PRs

        Returns:
            Dictionary with statistics
        """
        if not prs:
            return {}

        stats = {
            "total": len(prs),
            "by_state": {},
            "by_labels": {},
            "date_range": {
                "oldest": None,
                "newest": None
            }
        }

        # Count by state
        for pr in prs:
            state = pr.get('state', 'unknown')

            # Determine if merged
            if pr.get('pull_request', {}).get('merged_at'):
                state = 'merged'

            stats["by_state"][state] = stats["by_state"].get(state, 0) + 1

            # Count labels
            for label in pr.get('labels', []):
                label_name = label.get('name', 'unknown')
                stats["by_labels"][label_name] = stats["by_labels"].get(label_name, 0) + 1

        # Date range
        if prs:
            dates = [pr.get('created_at') for pr in prs if pr.get('created_at')]
            if dates:
                stats["date_range"]["oldest"] = min(dates)
                stats["date_range"]["newest"] = max(dates)

        return stats

    def compress_pr_data(self, pr: Dict) -> str:
        """
        Compress PR data to essential information only

        Args:
            pr: Full PR dictionary

        Returns:
            Compressed string representation
        """
        # Extract essential info
        number = pr.get('number', 'N/A')
        title = pr.get('title', 'No title')
        body = (pr.get('body') or '')[:300]  # Limit body to 300 chars, handle None
        labels = [label.get('name', '') for label in pr.get('labels', [])]
        state = pr.get('state', 'unknown')

        # Check if merged
        if pr.get('pull_request', {}).get('merged_at'):
            state = 'merged'

        created_at = pr.get('created_at', 'N/A')
        comments = pr.get('comments', 0)

        # Build base compressed info
        compressed = f"""
PR #{number}: {title}
State: {state}
Created: {created_at}
Labels: {', '.join(labels) if labels else 'None'}
Comments: {comments}
Description: {body}...
""".strip()

        # Add file information if available
        files = pr.get('files', [])
        if files:
            file_count = len(files)
            total_additions = sum(f.get('additions', 0) for f in files)
            total_deletions = sum(f.get('deletions', 0) for f in files)

            # Detect technologies from file extensions
            technologies = set()
            file_details = []

            # Filter out non-informative files (configs, locks, etc.)
            exclude_patterns = ['.lock', 'package-lock.json', 'yarn.lock', 'poetry.lock',
                              '.idea/', '.vscode/', 'node_modules/', '__pycache__/']

            informative_files = [
                f for f in files
                if not any(pattern in f.get('filename', '') for pattern in exclude_patterns)
            ]

            # Prioritize code files for patch display
            code_extensions = ['.py', '.ts', '.tsx', '.js', '.jsx', '.java', '.go', '.rs',
                             '.cpp', '.c', '.rb', '.php', '.vue', '.html', '.css', '.scss']
            files_with_patch = [
                f for f in informative_files
                if f.get('patch') and any(f.get('filename', '').endswith(ext) for ext in code_extensions)
            ]

            for file_data in informative_files[:10]:  # Limit to first 10 files to save tokens
                filename = file_data.get('filename', '')
                status = file_data.get('status', '')
                additions = file_data.get('additions', 0)
                deletions = file_data.get('deletions', 0)

                # Extract technology from extension
                if '.' in filename:
                    ext = filename.split('.')[-1].lower()
                    tech_map = {
                        'py': 'Python',
                        'js': 'JavaScript',
                        'jsx': 'React',
                        'ts': 'TypeScript',
                        'tsx': 'React/TypeScript',
                        'java': 'Java',
                        'go': 'Go',
                        'rs': 'Rust',
                        'cpp': 'C++',
                        'c': 'C',
                        'rb': 'Ruby',
                        'php': 'PHP',
                        'vue': 'Vue',
                        'html': 'HTML',
                        'css': 'CSS',
                        'scss': 'SCSS',
                        'yaml': 'YAML',
                        'yml': 'YAML',
                        'json': 'JSON',
                        'md': 'Markdown',
                        'sql': 'SQL',
                        'sh': 'Shell',
                    }
                    if ext in tech_map:
                        technologies.add(tech_map[ext])

                file_details.append(f"  - {filename}: +{additions} -{deletions} ({status})")

            # Add files section to compressed output
            compressed += f"\n\nFiles changed ({file_count}): +{total_additions} -{total_deletions}"
            if technologies:
                compressed += f"\nTechnologies: {', '.join(sorted(technologies))}"
            compressed += "\n" + "\n".join(file_details)

            if len(informative_files) > 10:
                compressed += f"\n  ... and {len(informative_files) - 10} more files"

            # Add key code changes section with patches (up to 5 files)
            if files_with_patch:
                compressed += "\n\nKey code changes:"
                for file_data in files_with_patch[:5]:  # Show up to 5 files with patches
                    filename = file_data.get('filename', '')
                    additions = file_data.get('additions', 0)
                    deletions = file_data.get('deletions', 0)
                    status = file_data.get('status', '')
                    patch = file_data.get('patch', '')

                    compressed += f"\n  - {filename}: +{additions} -{deletions} ({status})"

                    # Extract key lines from patch (imports, class/function definitions)
                    if patch:
                        key_lines = []
                        for line in patch.split('\n'):
                            # Show added lines that are imports or definitions
                            if line.startswith('+') and not line.startswith('+++'):
                                stripped = line[1:].strip()
                                # Include imports, class/function defs, decorators
                                if any(keyword in stripped for keyword in [
                                    'import ', 'from ', 'class ', 'def ', 'function ',
                                    'const ', 'let ', 'var ', 'interface ', 'type ',
                                    '@', 'async ', 'export '
                                ]):
                                    key_lines.append(f"    {line}")
                                    if len(key_lines) >= 3:  # Max 3 lines per file
                                        break

                        if key_lines:
                            compressed += "\n" + "\n".join(key_lines)

        return compressed