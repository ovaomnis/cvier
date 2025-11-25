"""
GitHub API client for fetching pull requests and repository data
"""

import time
import requests
from typing import List, Dict, Optional, Tuple, Union
from datetime import datetime
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn


console = Console()


class GitHubAPIError(Exception):
    """Custom exception for GitHub API errors"""
    pass


class RateLimitError(GitHubAPIError):
    """Exception raised when rate limit is exceeded"""
    pass


class GitHubClient:
    """Client for interacting with GitHub API"""

    def __init__(self, token: str):
        self.token = token
        self.headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json"
        }
        self.base_url = "https://api.github.com"
        self.username: Optional[str] = None
        self._rate_limit_remaining: Optional[int] = None
        self._rate_limit_reset: Optional[int] = None

    def _handle_rate_limit(self, response: requests.Response):
        """Handle rate limiting from GitHub API"""
        self._rate_limit_remaining = int(response.headers.get('X-RateLimit-Remaining', 0))
        self._rate_limit_reset = int(response.headers.get('X-RateLimit-Reset', 0))

        if response.status_code == 403 and self._rate_limit_remaining == 0:
            reset_time = datetime.fromtimestamp(self._rate_limit_reset)
            wait_seconds = (reset_time - datetime.now()).total_seconds()

            if wait_seconds > 0:
                console.print(f"\n[yellow]⚠️  Rate limit exceeded. Waiting {int(wait_seconds)} seconds...[/yellow]")
                time.sleep(wait_seconds + 1)
                return True
        return False

    def _make_request(self, url: str, params: Optional[Dict] = None) -> requests.Response:
        """Make HTTP request with error handling and rate limiting"""
        max_retries = 3
        retry_count = 0

        while retry_count < max_retries:
            try:
                response = requests.get(url, headers=self.headers, params=params, timeout=30)

                # Handle rate limiting
                if self._handle_rate_limit(response):
                    continue

                response.raise_for_status()
                return response

            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 401:
                    raise GitHubAPIError("Invalid GitHub token. Please check your credentials.")
                elif e.response.status_code == 403:
                    raise GitHubAPIError("Access forbidden. Make sure your token has 'repo' scope.")
                elif e.response.status_code == 404:
                    raise GitHubAPIError("Resource not found. Check organization/repository name.")
                else:
                    retry_count += 1
                    if retry_count >= max_retries:
                        raise GitHubAPIError(f"HTTP Error: {e}")
                    console.print(f"[yellow]Retrying... ({retry_count}/{max_retries})[/yellow]")
                    time.sleep(2 ** retry_count)  # Exponential backoff

            except requests.exceptions.RequestException as e:
                retry_count += 1
                if retry_count >= max_retries:
                    raise GitHubAPIError(f"Request failed: {e}")
                console.print(f"[yellow]Retrying... ({retry_count}/{max_retries})[/yellow]")
                time.sleep(2 ** retry_count)

        raise GitHubAPIError("Max retries exceeded")

    def get_current_user(self) -> Dict:
        """Get authenticated user information"""
        response = self._make_request(f"{self.base_url}/user")
        user_data = response.json()
        self.username = user_data['login']
        return user_data

    def get_organizations(self) -> List[Dict]:
        """Get all organizations for authenticated user"""
        orgs = []
        page = 1
        per_page = 100

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("[cyan]Fetching organizations...", total=None)

            while True:
                response = self._make_request(
                    f"{self.base_url}/user/orgs",
                    params={"per_page": per_page, "page": page}
                )
                page_orgs = response.json()

                if not page_orgs:
                    break

                orgs.extend(page_orgs)
                progress.update(task, description=f"[cyan]Fetching organizations... ({len(orgs)} found)")
                page += 1

            progress.update(task, completed=True)

        return orgs

    def get_repositories(self, org_name: str) -> List[Dict]:
        """Get all repositories from organization"""
        repos = []
        page = 1
        per_page = 100

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task(f"[cyan]Fetching repositories from {org_name}...", total=None)

            while True:
                response = self._make_request(
                    f"{self.base_url}/orgs/{org_name}/repos",
                    params={"per_page": per_page, "page": page, "type": "all"}
                )
                page_repos = response.json()

                if not page_repos:
                    break

                repos.extend(page_repos)
                progress.update(task, description=f"[cyan]Fetching repositories... ({len(repos)} found)")
                page += 1

            progress.update(task, completed=True)

        return repos

    def get_pull_requests(
        self,
        owner: str,
        repo: str,
        author: str,
        state: Union[str, List[str]] = "all",
        labels: Optional[List[str]] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
        merged_only: bool = False
    ) -> List[Dict]:
        """
        Get all pull requests by author from repository

        Args:
            owner: Repository owner (organization or user)
            repo: Repository name
            author: GitHub username of PR author
            state: PR state (all, open, closed, merged) or list of states ["open", "merged"]
            labels: Filter by labels
            since: Filter PRs created after this date (ISO 8601 format)
            until: Filter PRs created before this date (ISO 8601 format)
            merged_only: If True, only return merged PRs (only works with closed state)

        Returns:
            List of pull request dictionaries
        """
        # Convert string to list for uniform processing
        if isinstance(state, str):
            states = [state]
        else:
            states = state

        # If "all" is in states, just fetch everything
        if "all" in states:
            return self._fetch_prs_by_state(
                owner, repo, author, "all", labels, since, until, merged_only
            )

        # Fetch PRs for each state and combine
        all_prs = []
        seen_numbers = set()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task(
                f"[cyan]Fetching PRs from {owner}/{repo}...",
                total=len(states)
            )

            for s in states:
                prs = self._fetch_prs_by_state(
                    owner, repo, author, s, labels, since, until, merged_only
                )

                # Add only unique PRs (deduplicate by number)
                for pr in prs:
                    pr_number = pr['number']
                    if pr_number not in seen_numbers:
                        all_prs.append(pr)
                        seen_numbers.add(pr_number)

                progress.update(
                    task,
                    advance=1,
                    description=f"[cyan]Fetching PRs... ({len(all_prs)} unique found)"
                )

        # Sort by created date (newest first)
        all_prs.sort(key=lambda x: x.get('created_at', ''), reverse=True)

        return all_prs

    def _fetch_prs_by_state(
        self,
        owner: str,
        repo: str,
        author: str,
        state: str,
        labels: Optional[List[str]] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
        merged_only: bool = False
    ) -> List[Dict]:
        """
        Internal method to fetch PRs by single state

        Returns:
            List of pull request dictionaries
        """
        prs = []
        page = 1
        per_page = 100

        # Build search query
        query_parts = [
            f"repo:{owner}/{repo}",
            "type:pr",
            f"author:{author}"
        ]

        if state == "merged":
            query_parts.append("is:merged")
        elif state != "all":
            query_parts.append(f"is:{state}")
            if merged_only and state == "closed":
                query_parts.append("is:merged")

        if labels:
            for label in labels:
                query_parts.append(f"label:{label}")

        if since:
            query_parts.append(f"created:>={since}")

        if until:
            query_parts.append(f"created:<={until}")

        query = " ".join(query_parts)

        while True:
            response = self._make_request(
                f"{self.base_url}/search/issues",
                params={
                    "q": query,
                    "per_page": per_page,
                    "page": page,
                    "sort": "created",
                    "order": "desc"
                }
            )
            data = response.json()

            if not data.get('items'):
                break

            prs.extend(data['items'])

            # Check if we have more pages
            if len(data['items']) < per_page:
                break

            page += 1

        return prs

    def get_pull_requests_from_multiple_repos(
        self,
        org_name: str,
        repo_names: List[str],
        author: str,
        state: Union[str, List[str]] = "all",
        labels: Optional[List[str]] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
        merged_only: bool = False
    ) -> Dict[str, List[Dict]]:
        """
        Get pull requests from multiple repositories

        Args:
            state: PR state (all, open, closed, merged) or list of states ["open", "merged"]

        Returns:
            Dictionary mapping repository name to list of PRs
        """
        results = {}

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("[cyan]Fetching PRs from repositories...", total=len(repo_names))

            for repo_name in repo_names:
                try:
                    prs = self.get_pull_requests(
                        org_name,
                        repo_name,
                        author,
                        state,
                        labels,
                        since,
                        until,
                        merged_only
                    )
                    results[repo_name] = prs
                    progress.update(
                        task,
                        advance=1,
                        description=f"[cyan]Processed {repo_name} ({len(prs)} PRs)"
                    )
                except GitHubAPIError as e:
                    console.print(f"[yellow]⚠️  Error fetching from {repo_name}: {e}[/yellow]")
                    results[repo_name] = []
                    progress.update(task, advance=1)

        return results

    def get_rate_limit_status(self) -> Tuple[int, int]:
        """
        Get current rate limit status

        Returns:
            Tuple of (remaining requests, reset timestamp)
        """
        response = self._make_request(f"{self.base_url}/rate_limit")
        data = response.json()
        core = data['resources']['core']
        return core['remaining'], core['reset']

    def get_pr_files(self, owner: str, repo: str, pr_number: int) -> List[Dict]:
        """
        Get list of files changed in a pull request

        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: Pull request number

        Returns:
            List of file dictionaries with filename, status, additions, deletions, etc.
        """
        files = []
        page = 1
        per_page = 100  # Max per page for files endpoint

        while True:
            response = self._make_request(
                f"{self.base_url}/repos/{owner}/{repo}/pulls/{pr_number}/files",
                params={"per_page": per_page, "page": page}
            )
            page_files = response.json()

            if not page_files:
                break

            files.extend(page_files)

            # GitHub API limits to 300 files per PR
            if len(page_files) < per_page or len(files) >= 300:
                break

            page += 1

        return files