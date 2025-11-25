#!/usr/bin/env python3
"""
GitHub PR Fetcher CLI
Interactive command-line tool for fetching and exporting pull requests from GitHub
"""

import sys
import os
import yaml
from typing import Optional, List
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt, Confirm
from rich.panel import Panel
from rich import print as rprint

from .config import config
from .github_api import GitHubClient, GitHubAPIError
from .exporters import JSONExporter, CSVExporter, MarkdownExporter
from .local_loader import LocalPRLoader
from .ai_analyzer import GroqAnalyzer
from .enricher import PREnricher


app = typer.Typer(
    name="github-pr-fetcher",
    help="Fetch and export pull requests from GitHub organizations and repositories",
    add_completion=False
)
console = Console()


def print_header():
    """Print CLI header"""
    console.print(Panel.fit(
        "[bold cyan]GitHub PR Fetcher[/bold cyan]\n"
        "Interactive tool for fetching and exporting pull requests",
        border_style="cyan"
    ))


def display_menu(items: List[dict], title: str, name_key: str, show_description: bool = False) -> Optional[dict]:
    """
    Display interactive menu and return selected item

    Args:
        items: List of items to display
        title: Menu title
        name_key: Key to use for item name
        show_description: Whether to show description column

    Returns:
        Selected item or None if cancelled
    """
    if not items:
        console.print(f"[yellow]⚠️  No {title.lower()} found[/yellow]")
        return None

    # Create table
    table = Table(title=title, show_header=True, header_style="bold cyan")
    table.add_column("#", style="dim", width=6)
    table.add_column("Name", style="cyan")

    if show_description:
        table.add_column("Description", style="dim")

    # Add rows
    for i, item in enumerate(items, 1):
        if show_description:
            desc = item.get('description', '') or 'N/A'
            # Truncate long descriptions
            if len(desc) > 50:
                desc = desc[:47] + "..."
            table.add_row(str(i), item[name_key], desc)
        else:
            table.add_row(str(i), item[name_key])

    console.print(table)
    console.print("[dim]Enter 0 to cancel[/dim]")

    while True:
        try:
            choice = Prompt.ask(
                f"\nSelect {title.lower()}",
                default="0"
            )

            choice_num = int(choice)

            if choice_num == 0:
                return None

            if 1 <= choice_num <= len(items):
                return items[choice_num - 1]

            console.print(f"[red]❌ Invalid choice. Please enter a number between 0 and {len(items)}[/red]")

        except ValueError:
            console.print("[red]❌ Invalid input. Please enter a number[/red]")
        except KeyboardInterrupt:
            console.print("\n[yellow]👋 Cancelled[/yellow]")
            return None


def select_multiple_items(items: List[dict], title: str, name_key: str) -> List[dict]:
    """
    Allow user to select multiple items from list

    Returns:
        List of selected items
    """
    if not items:
        console.print(f"[yellow]⚠️  No {title.lower()} found[/yellow]")
        return []

    # Create table
    table = Table(title=title, show_header=True, header_style="bold cyan")
    table.add_column("#", style="dim", width=6)
    table.add_column("Name", style="cyan")

    for i, item in enumerate(items, 1):
        table.add_row(str(i), item[name_key])

    console.print(table)
    console.print("[dim]Enter comma-separated numbers (e.g., 1,3,5) or 'all' for all items[/dim]")
    console.print("[dim]Enter 0 to cancel[/dim]")

    while True:
        try:
            choice = Prompt.ask(
                f"\nSelect {title.lower()}",
                default="all"
            )

            if choice == "0":
                return []

            if choice.lower() == "all":
                return items

            # Parse comma-separated numbers
            indices = [int(x.strip()) for x in choice.split(",")]

            # Validate all indices
            if all(1 <= idx <= len(items) for idx in indices):
                return [items[idx - 1] for idx in indices]

            console.print(f"[red]❌ Invalid choice. Please enter numbers between 1 and {len(items)}[/red]")

        except ValueError:
            console.print("[red]❌ Invalid input. Please enter comma-separated numbers[/red]")
        except KeyboardInterrupt:
            console.print("\n[yellow]👋 Cancelled[/yellow]")
            return []


@app.command()
def interactive(
    token: Optional[str] = typer.Option(None, "--token", "-t", help="GitHub personal access token"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output directory"),
):
    """
    Interactive mode - guided workflow for fetching PRs
    """
    print_header()

    # Get token
    if not token:
        token = config.github_token
        if not token:
            console.print("\n[yellow]🔑 GitHub token not found in environment[/yellow]")
            token = Prompt.ask("Enter your GitHub token", password=True)

    try:
        # Initialize client
        client = GitHubClient(token)

        # Get current user
        console.print("\n[cyan]🔍 Authenticating...[/cyan]")
        user = client.get_current_user()
        console.print(f"[green]✅ Authenticated as: {user['login']}[/green]")

        # Get organizations
        orgs = client.get_organizations()

        if not orgs:
            console.print("[red]❌ No organizations found[/red]")
            raise typer.Exit(1)

        console.print(f"[green]✅ Found {len(orgs)} organizations[/green]")

        # Select organization
        selected_org = display_menu(orgs, "Organizations", "login")
        if not selected_org:
            console.print("\n[yellow]👋 Cancelled[/yellow]")
            raise typer.Exit(0)

        org_name = selected_org['login']
        console.print(f"\n[green]✅ Selected: {org_name}[/green]")

        # Get repositories
        repos = client.get_repositories(org_name)

        if not repos:
            console.print("[red]❌ No repositories found[/red]")
            raise typer.Exit(1)

        console.print(f"[green]✅ Found {len(repos)} repositories[/green]")

        # Ask: single or multiple repos
        mode = Prompt.ask(
            "\nSelect mode",
            choices=["single", "multiple"],
            default="single"
        )

        if mode == "single":
            # Select single repository
            selected_repo = display_menu(repos, "Repositories", "name", show_description=True)
            if not selected_repo:
                console.print("\n[yellow]👋 Cancelled[/yellow]")
                raise typer.Exit(0)

            repo_names = [selected_repo['name']]
        else:
            # Select multiple repositories
            selected_repos = select_multiple_items(repos, "Repositories", "name")
            if not selected_repos:
                console.print("\n[yellow]👋 Cancelled[/yellow]")
                raise typer.Exit(0)

            repo_names = [repo['name'] for repo in selected_repos]

        console.print(f"\n[green]✅ Selected {len(repo_names)} repository(ies)[/green]")

        # PR filters
        console.print("\n[cyan]🔍 Configure filters[/cyan]")

        # State - multiple selection
        console.print("\n[cyan]Select PR state(s):[/cyan]")
        console.print("1. All")
        console.print("2. Open")
        console.print("3. Closed")
        console.print("4. Merged")
        console.print("\n[dim]Enter comma-separated numbers (e.g., 2,4 for open+merged) or 1 for all[/dim]")

        state_input = Prompt.ask("Select state(s)", default="1")

        state_mapping = {
            "1": "all",
            "2": "open",
            "3": "closed",
            "4": "merged"
        }

        # Parse state selection
        if state_input == "1":
            state = "all"
        else:
            selected_numbers = [n.strip() for n in state_input.split(",")]
            selected_states = []
            for num in selected_numbers:
                if num in state_mapping:
                    selected_states.append(state_mapping[num])

            if len(selected_states) == 1:
                state = selected_states[0]
            else:
                state = selected_states

        # Merged only for closed (only if single state selected)
        merged_only = False
        if isinstance(state, str) and state == "closed":
            merged_only = Confirm.ask("Only merged PRs?", default=False)

        # Date filters
        use_date_filter = Confirm.ask("Filter by date range?", default=False)
        since = None
        until = None

        if use_date_filter:
            since = Prompt.ask("Created after (YYYY-MM-DD)", default="")
            until = Prompt.ask("Created before (YYYY-MM-DD)", default="")

            if not since:
                since = None
            if not until:
                until = None

        # Export format
        export_format = Prompt.ask(
            "Export format",
            choices=["json", "csv", "markdown", "all"],
            default="json"
        )

        # Output directory
        if not output:
            output = Prompt.ask("Output directory", default="./github_prs")

        output_path = Path(output)

        # Fetch PRs
        if len(repo_names) == 1:
            # Single repository
            prs = client.get_pull_requests(
                org_name,
                repo_names[0],
                user['login'],
                state,
                since=since,
                until=until,
                merged_only=merged_only
            )

            if not prs:
                console.print("[yellow]⚠️  No PRs found[/yellow]")
                raise typer.Exit(0)

            console.print(f"\n[green]✅ Found {len(prs)} PRs[/green]")

            # Export
            if export_format in ["json", "all"]:
                exporter = JSONExporter(output_path)
                exporter.export(prs, org_name, repo_names[0])

            if export_format in ["csv", "all"]:
                exporter = CSVExporter(output_path)
                exporter.export(prs, org_name, repo_names[0])

            if export_format in ["markdown", "all"]:
                exporter = MarkdownExporter(output_path)
                exporter.export(prs, org_name, repo_names[0])

        else:
            # Multiple repositories
            repo_prs = client.get_pull_requests_from_multiple_repos(
                org_name,
                repo_names,
                user['login'],
                state,
                since=since,
                until=until,
                merged_only=merged_only
            )

            total_prs = sum(len(prs) for prs in repo_prs.values())

            if total_prs == 0:
                console.print("[yellow]⚠️  No PRs found[/yellow]")
                raise typer.Exit(0)

            console.print(f"\n[green]✅ Found {total_prs} PRs across {len(repo_names)} repositories[/green]")

            # Export
            if export_format in ["json", "all"]:
                exporter = JSONExporter(output_path)
                exporter.export_multiple(repo_prs, org_name)

            if export_format in ["csv", "all"]:
                exporter = CSVExporter(output_path)
                exporter.export_multiple(repo_prs, org_name)

            if export_format in ["markdown", "all"]:
                exporter = MarkdownExporter(output_path)
                exporter.export_multiple(repo_prs, org_name)

        console.print(f"\n[green]🎉 Done! Check {output_path} for exported data[/green]")

    except GitHubAPIError as e:
        console.print(f"\n[red]❌ Error: {e}[/red]")
        raise typer.Exit(1)
    except KeyboardInterrupt:
        console.print("\n\n[yellow]👋 Cancelled by user[/yellow]")
        raise typer.Exit(0)
    except Exception as e:
        console.print(f"\n[red]❌ Unexpected error: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def fetch(
    org: str = typer.Argument(..., help="Organization name"),
    repo: Optional[str] = typer.Option(None, "--repo", "-r", help="Repository name (if not specified, fetches from all repos)"),
    author: Optional[str] = typer.Option(None, "--author", "-a", help="PR author (defaults to authenticated user)"),
    state: str = typer.Option("all", "--state", "-s", help="PR state: all, open, closed, merged. Use comma-separated for multiple: open,merged"),
    merged_only: bool = typer.Option(False, "--merged-only", "-m", help="Only fetch merged PRs (works with closed state)"),
    format: str = typer.Option("json", "--format", "-f", help="Export format: json, csv, markdown, all"),
    output: str = typer.Option("./github_prs", "--output", "-o", help="Output directory"),
    token: Optional[str] = typer.Option(None, "--token", "-t", help="GitHub personal access token"),
    include_files: bool = typer.Option(False, "--include-files", help="Fetch and include file change data for each PR"),
):
    """
    Fetch PRs from specific organization/repository (non-interactive)
    """
    print_header()

    # Get token
    if not token:
        token = config.github_token
        if not token:
            console.print("[red]❌ GitHub token not found. Set GITHUB_TOKEN or use --token[/red]")
            raise typer.Exit(1)

    try:
        # Initialize client
        client = GitHubClient(token)

        # Get current user
        user = client.get_current_user()
        pr_author = author or user['login']

        console.print(f"[cyan]🔍 Fetching PRs by {pr_author} from {org}[/cyan]")

        # Parse state (support comma-separated values)
        if "," in state:
            parsed_state = [s.strip() for s in state.split(",")]
        else:
            parsed_state = state

        output_path = Path(output)

        if repo:
            # Single repository
            prs = client.get_pull_requests(org, repo, pr_author, parsed_state, merged_only=merged_only)

            if not prs:
                console.print("[yellow]⚠️  No PRs found[/yellow]")
                raise typer.Exit(0)

            console.print(f"[green]✅ Found {len(prs)} PRs[/green]")

            # Export
            if format in ["json", "all"]:
                exporter = JSONExporter(output_path)
                exporter.export(prs, org, repo)

            if format in ["csv", "all"]:
                exporter = CSVExporter(output_path)
                exporter.export(prs, org, repo)

            if format in ["markdown", "all"]:
                exporter = MarkdownExporter(output_path)
                exporter.export(prs, org, repo)

            # Enrich with file data if requested
            if include_files and format in ["json", "all"]:
                console.print(f"\n[cyan]📂 Enriching PRs with file data...[/cyan]")
                enricher = PREnricher(client)
                repo_path = output_path / org / repo
                stats = enricher.enrich_directory(repo_path, org, repo)

                if stats:
                    console.print(f"\n[green]✅ Enrichment complete:[/green]")
                    console.print(f"  Enriched: {stats.get('enriched', 0)}/{stats.get('total', 0)} PRs")

        else:
            # All repositories in organization
            repos = client.get_repositories(org)
            repo_names = [r['name'] for r in repos]

            repo_prs = client.get_pull_requests_from_multiple_repos(
                org,
                repo_names,
                pr_author,
                parsed_state,
                merged_only=merged_only
            )

            total_prs = sum(len(prs) for prs in repo_prs.values())

            if total_prs == 0:
                console.print("[yellow]⚠️  No PRs found[/yellow]")
                raise typer.Exit(0)

            console.print(f"[green]✅ Found {total_prs} PRs[/green]")

            # Export
            if format in ["json", "all"]:
                exporter = JSONExporter(output_path)
                exporter.export_multiple(repo_prs, org)

            if format in ["csv", "all"]:
                exporter = CSVExporter(output_path)
                exporter.export_multiple(repo_prs, org)

            if format in ["markdown", "all"]:
                exporter = MarkdownExporter(output_path)
                exporter.export_multiple(repo_prs, org)

            # Enrich with file data if requested
            if include_files and format in ["json", "all"]:
                console.print(f"\n[cyan]📂 Enriching PRs with file data...[/cyan]")
                enricher = PREnricher(client)
                org_path = output_path / org
                stats = enricher.enrich_organization(org_path, org)

                if stats:
                    console.print(f"\n[green]✅ Enrichment complete:[/green]")
                    console.print(f"  Enriched: {stats.get('enriched', 0)}/{stats.get('total', 0)} PRs across {stats.get('repositories', 0)} repositories")

        console.print(f"\n[green]🎉 Done! Check {output_path} for exported data[/green]")

    except GitHubAPIError as e:
        console.print(f"\n[red]❌ Error: {e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"\n[red]❌ Unexpected error: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def rate_limit(
    token: Optional[str] = typer.Option(None, "--token", "-t", help="GitHub personal access token"),
):
    """
    Check GitHub API rate limit status
    """
    # Get token
    if not token:
        token = config.github_token
        if not token:
            console.print("[red]❌ GitHub token not found[/red]")
            raise typer.Exit(1)

    try:
        client = GitHubClient(token)
        remaining, reset_timestamp = client.get_rate_limit_status()

        from datetime import datetime
        reset_time = datetime.fromtimestamp(reset_timestamp)

        table = Table(title="GitHub API Rate Limit", show_header=True, header_style="bold cyan")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Remaining Requests", str(remaining))
        table.add_row("Reset Time", reset_time.strftime("%Y-%m-%d %H:%M:%S"))

        console.print(table)

    except GitHubAPIError as e:
        console.print(f"[red]❌ Error: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def analyze(
    input_path: str = typer.Argument(..., help="Path to directory with PR JSON files"),
    fields: Optional[str] = typer.Option(None, "--fields", "-f", help="Comma-separated list of fields to fill"),
    batch_size: int = typer.Option(15, "--batch-size", "-b", help="Number of PRs per batch"),
    output: str = typer.Option("resume.yaml", "--output", "-o", help="Output file path"),
    format: str = typer.Option("yaml", "--format", help="Output format: yaml, json"),
    groq_key: Optional[str] = typer.Option(None, "--groq-key", help="Groq API key"),
    recursive: bool = typer.Option(False, "--recursive", "-r", help="Search subdirectories recursively"),
):
    """
    Analyze PRs from local files and generate AI-powered resume
    """
    print_header()

    # Get Groq API key
    if not groq_key:
        groq_key = os.getenv("GROQ_API_KEY")
        if not groq_key:
            console.print("[red]❌ Groq API key not found. Set GROQ_API_KEY or use --groq-key[/red]")
            raise typer.Exit(1)

    try:
        # Load PRs from local files
        loader = LocalPRLoader(Path(input_path))
        console.print(f"\n[cyan]📂 Loading PRs from {input_path}...[/cyan]")

        prs = loader.load_prs_from_directory(recursive=recursive)

        if not prs:
            console.print("[yellow]⚠️  No PRs found in the specified directory[/yellow]")
            raise typer.Exit(0)

        console.print(f"[green]✅ Loaded {len(prs)} PRs[/green]")

        # Show statistics
        stats = loader.get_statistics(prs)
        if stats:
            console.print(f"\n[cyan]📊 Statistics:[/cyan]")
            console.print(f"  Total: {stats['total']}")
            for state, count in stats.get('by_state', {}).items():
                console.print(f"  {state.capitalize()}: {count}")

        # Get fields to fill
        if not fields:
            # Default fields
            default_fields = [
                "Key Achievements",
                "Technologies Used",
                "Projects Completed",
                "Bug Fixes"
            ]

            console.print("\n[cyan]📝 Default fields:[/cyan]")
            for i, field in enumerate(default_fields, 1):
                console.print(f"  {i}. {field}")

            use_default = Confirm.ask("\nUse default fields?", default=True)

            if use_default:
                fields_list = default_fields
            else:
                custom_fields = Prompt.ask("Enter comma-separated field names")
                fields_list = [f.strip() for f in custom_fields.split(",")]
        else:
            fields_list = [f.strip() for f in fields.split(",")]

        console.print(f"\n[green]✅ Fields to analyze: {', '.join(fields_list)}[/green]")

        # Initialize Groq analyzer
        console.print(f"\n[cyan]🤖 Initializing AI analyzer (model: llama-3.3-70b-versatile)...[/cyan]")
        analyzer = GroqAnalyzer(api_key=groq_key)

        # Analyze PRs
        result = analyzer.analyze_prs(prs, fields_list, batch_size)

        # Prepare output
        output_data = {
            "metadata": {
                "total_prs": len(prs),
                "input_path": str(input_path),
                "analyzed_at": __import__('datetime').datetime.now().isoformat(),
                "statistics": stats
            },
            "fields": result.get("fields", {}),
            "summary": result.get("summary", "")
        }

        # Save output
        output_path = Path(output)

        if format == "yaml":
            with open(output_path, 'w', encoding='utf-8') as f:
                yaml.dump(output_data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        else:  # json
            import json
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(output_data, f, indent=2, ensure_ascii=False)

        console.print(f"\n[green]🎉 Resume generated successfully![/green]")
        console.print(f"[green]📄 Saved to: {output_path}[/green]")

        # Display summary preview
        console.print("\n[cyan]📝 Summary Preview:[/cyan]")
        summary_lines = result.get("summary", "").split('\n')
        for line in summary_lines[:5]:  # Show first 5 lines
            console.print(f"  {line}")
        if len(summary_lines) > 5:
            console.print(f"  ... ({len(summary_lines) - 5} more lines)")

    except FileNotFoundError as e:
        console.print(f"[red]❌ Directory not found: {input_path}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]❌ Error: {e}[/red]")
        import traceback
        traceback.print_exc()
        raise typer.Exit(1)


@app.command()
def enrich(
    input_path: str = typer.Argument(..., help="Path to directory with PR JSON files"),
    owner: str = typer.Option(..., "--owner", "-o", help="Repository owner (organization name)"),
    repo: Optional[str] = typer.Option(None, "--repo", "-r", help="Repository name (if not specified, processes all repos in org)"),
    token: Optional[str] = typer.Option(None, "--token", "-t", help="GitHub personal access token"),
    recursive: bool = typer.Option(False, "--recursive", help="Process subdirectories recursively"),
):
    """
    Enrich existing PR JSON files with file change data from GitHub API
    """
    print_header()

    # Get token
    if not token:
        token = config.github_token
        if not token:
            console.print("[red]❌ GitHub token not found. Set GITHUB_TOKEN or use --token[/red]")
            raise typer.Exit(1)

    try:
        # Initialize GitHub client
        client = GitHubClient(token)
        console.print(f"\n[cyan]🔐 Authenticated with GitHub[/cyan]")

        # Check rate limit
        remaining, reset = client.get_rate_limit_status()
        console.print(f"[cyan]📊 Rate limit: {remaining} requests remaining[/cyan]")

        # Initialize enricher
        enricher = PREnricher(client)

        input_dir = Path(input_path)

        if not input_dir.exists():
            console.print(f"[red]❌ Directory not found: {input_path}[/red]")
            raise typer.Exit(1)

        # Determine mode: single repo or whole organization
        if repo:
            # Single repository mode
            console.print(f"\n[bold cyan]Enriching repository: {owner}/{repo}[/bold cyan]")
            stats = enricher.enrich_directory(input_dir, owner, repo, recursive=recursive)
        else:
            # Organization mode - process all repos
            console.print(f"\n[bold cyan]Enriching organization: {owner}[/bold cyan]")
            stats = enricher.enrich_organization(input_dir, owner)

        # Display summary
        console.print("\n[bold cyan]📊 Enrichment Summary:[/bold cyan]")
        console.print(f"  Total PRs: {stats.get('total', 0)}")
        console.print(f"  ✅ Enriched: {stats.get('enriched', 0)}")
        console.print(f"  ⏭️  Skipped (already enriched): {stats.get('skipped', 0)}")
        console.print(f"  ❌ Failed: {stats.get('failed', 0)}")

        if stats.get('repositories'):
            console.print(f"  📁 Repositories processed: {stats['repositories']}")

        # Final rate limit check
        remaining_after, _ = client.get_rate_limit_status()
        used = remaining - remaining_after
        console.print(f"\n[cyan]📊 API requests used: {used}[/cyan]")
        console.print(f"[cyan]📊 Rate limit remaining: {remaining_after}[/cyan]")

        if stats.get('enriched', 0) > 0:
            console.print(f"\n[green]🎉 Successfully enriched {stats['enriched']} PRs![/green]")
        else:
            console.print(f"\n[yellow]ℹ️  No PRs were enriched (all may be already enriched or failed)[/yellow]")

    except GitHubAPIError as e:
        console.print(f"\n[red]❌ GitHub API Error: {e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"\n[red]❌ Error: {e}[/red]")
        import traceback
        traceback.print_exc()
        raise typer.Exit(1)


def main():
    """Main entry point"""
    app()


if __name__ == "__main__":
    main()