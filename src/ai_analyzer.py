"""
AI-powered PR analysis using Groq API
Analyzes PRs with batching to avoid token limits
"""

import os
import json
from typing import List, Dict, Optional
from groq import Groq
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from .local_loader import LocalPRLoader


console = Console()


class PRBatcher:
    """Handles batching of PRs for LLM processing"""

    def __init__(self, batch_size: int = 15):
        self.batch_size = batch_size

    def create_batches(self, prs: List[Dict]) -> List[List[Dict]]:
        """
        Split PRs into manageable batches

        Args:
            prs: List of PR dictionaries

        Returns:
            List of batches (each batch is a list of PRs)
        """
        if not prs:
            return []

        batches = []
        for i in range(0, len(prs), self.batch_size):
            batch = prs[i:i + self.batch_size]
            batches.append(batch)

        return batches

    def estimate_tokens(self, text: str) -> int:
        """
        Rough estimation of token count

        Args:
            text: Text to estimate

        Returns:
            Estimated token count
        """
        # Rough estimation: ~4 characters per token
        return len(text) // 4


class GroqAnalyzer:
    """Groq AI analyzer with batching support"""

    def __init__(self, api_key: str, model: str = "llama-3.3-70b-versatile"):
        self.client = Groq(api_key=api_key)
        self.model = model
        self.batcher = PRBatcher()
        self.loader = None

    def analyze_prs(
        self,
        prs: List[Dict],
        fields: List[str],
        batch_size: int = 15
    ) -> Dict:
        """
        Analyze PRs with batching

        Args:
            prs: List of PR dictionaries
            fields: List of field names to fill
            batch_size: Number of PRs per batch

        Returns:
            Dictionary with filled fields and summary
        """
        if not prs:
            console.print("[yellow]⚠️  No PRs to analyze[/yellow]")
            return {"fields": {}, "summary": "No data available"}

        self.batcher.batch_size = batch_size
        batches = self.batcher.create_batches(prs)

        console.print(f"\n[cyan]📊 Analysis Plan:[/cyan]")
        console.print(f"  Total PRs: {len(prs)}")
        console.print(f"  Batches: {len(batches)}")
        console.print(f"  Batch size: {batch_size}\n")

        # Analyze each batch
        batch_results = []

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console
        ) as progress:
            task = progress.add_task(
                "[cyan]Analyzing batches...",
                total=len(batches)
            )

            for i, batch in enumerate(batches, 1):
                progress.update(
                    task,
                    description=f"[cyan]Analyzing batch {i}/{len(batches)}..."
                )

                result = self._analyze_batch(batch, fields)
                batch_results.append(result)

                progress.update(task, advance=1)

        # Aggregate results
        console.print("\n[cyan]🔄 Aggregating results...[/cyan]")
        final_result = self._aggregate_results(batch_results, fields, len(prs))

        return final_result

    def _analyze_batch(self, batch: List[Dict], fields: List[str]) -> Dict:
        """
        Analyze single batch of PRs

        Args:
            batch: List of PR dictionaries
            fields: Fields to extract

        Returns:
            Partial analysis result
        """
        # Initialize loader if needed
        if not self.loader:
            self.loader = LocalPRLoader(Path("."))

        # Compress PR data
        compressed_prs = []
        for pr in batch:
            compressed = self.loader.compress_pr_data(pr)
            compressed_prs.append(compressed)

        prs_text = "\n\n---\n\n".join(compressed_prs)

        # Create prompt
        prompt = f"""You are analyzing pull requests for a professional resume. Write from the developer's perspective in first person.

Analyze these {len(batch)} pull requests and extract information for the following fields:
{', '.join(fields)}

Pull Requests (with code snippets):
{prs_text}

Instructions:
1. Analyze code patches to identify EXACT technologies, frameworks, and libraries used (e.g., "Chakra UI", "Framer Motion", not just "React")
2. Extract specific features and technical achievements from the code
3. Write in first person professional style: "I implemented...", "I developed...", "I architected..."
4. Be specific about technical decisions and impact

Output must be valid JSON with this structure:
{{
  "fields": {{
    "{fields[0]}": ["I implemented feature X using technology Y", "I developed..."],
    ...
  }},
  "partial_summary": "Brief first-person summary: I worked on..., I implemented..."
}}

Focus on technical depth, specific technologies from code, and professional achievements."""

        try:
            response = self.client.chat.completions.create(
                messages=[
                    {
                        "role": "system",
                        "content": "You are writing a professional resume from the developer's perspective. Analyze code changes to identify exact technologies and write in first person: 'I implemented...', 'I developed...', 'I architected...'. Be specific about technologies, frameworks, and libraries seen in the code."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                model=self.model,
                temperature=0.3,
                max_tokens=4000
            )

            content = response.choices[0].message.content.strip()

            # Try to parse JSON from response
            # Sometimes LLM wraps JSON in markdown code blocks
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]

            result = json.loads(content.strip())
            return result

        except json.JSONDecodeError as e:
            console.print(f"[yellow]⚠️  Failed to parse JSON from LLM response: {e}[/yellow]")
            # Return empty structure
            return {
                "fields": {field: [] for field in fields},
                "partial_summary": ""
            }
        except Exception as e:
            console.print(f"[red]❌ Error analyzing batch: {e}[/red]")
            return {
                "fields": {field: [] for field in fields},
                "partial_summary": ""
            }

    def _aggregate_results(self, batch_results: List[Dict], fields: List[str], total_prs: int) -> Dict:
        """
        Aggregate all batch results into final output

        Args:
            batch_results: List of batch analysis results
            fields: Field names
            total_prs: Total number of PRs analyzed

        Returns:
            Final aggregated result
        """
        # Prepare aggregation prompt
        batch_summaries = []
        for i, result in enumerate(batch_results, 1):
            batch_summaries.append(f"Batch {i}: {result.get('partial_summary', '')}")

        all_results_text = json.dumps(batch_results, indent=2)

        prompt = f"""Combine these {len(batch_results)} partial analysis results into a final comprehensive resume output.

Partial Results:
{all_results_text}

Batch Summaries:
{chr(10).join(batch_summaries)}

Total PRs analyzed: {total_prs}

Tasks:
1. Merge all field lists (combine items, remove duplicates, keep most important)
2. Create comprehensive first-person professional summary (2-3 paragraphs)
3. Write as the developer: "I implemented...", "I developed...", "I architected..."
4. Ensure professional tone suitable for a resume

Output must be valid JSON:
{{
  "fields": {{
    "{fields[0]}": ["I implemented X", "I developed Y", ...],
    ...
  }},
  "summary": "First-person professional summary: I worked on... I implemented... I achieved..."
}}

The summary should:
- Highlight key technical achievements and impact
- Specify exact technologies, frameworks, and tools used
- Demonstrate technical depth and leadership
- Be written in professional first-person style suitable for a resume"""

        try:
            response = self.client.chat.completions.create(
                messages=[
                    {
                        "role": "system",
                        "content": "You are writing a professional technical resume from the developer's perspective. Write in first person using formal professional style: 'I implemented...', 'I developed...', 'I architected...'. Create comprehensive summaries that highlight technical achievements, exact technologies used, and measurable impact."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                model=self.model,
                temperature=0.3,
                max_tokens=6000
            )

            content = response.choices[0].message.content.strip()

            # Clean markdown code blocks if present
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]

            result = json.loads(content.strip())

            # Ensure all fields are present
            if "fields" not in result:
                result["fields"] = {}

            for field in fields:
                if field not in result["fields"]:
                    result["fields"][field] = []

            return result

        except json.JSONDecodeError as e:
            console.print(f"[yellow]⚠️  Failed to parse aggregation JSON: {e}[/yellow]")
            # Fallback: manually merge results
            return self._manual_aggregation(batch_results, fields)
        except Exception as e:
            console.print(f"[red]❌ Error aggregating results: {e}[/red]")
            return self._manual_aggregation(batch_results, fields)

    def _manual_aggregation(self, batch_results: List[Dict], fields: List[str]) -> Dict:
        """
        Fallback manual aggregation if LLM fails

        Args:
            batch_results: Batch results
            fields: Field names

        Returns:
            Manually aggregated result
        """
        merged_fields = {field: [] for field in fields}

        # Combine all items
        for result in batch_results:
            result_fields = result.get("fields", {})
            for field in fields:
                items = result_fields.get(field, [])
                merged_fields[field].extend(items)

        # Remove duplicates
        for field in fields:
            merged_fields[field] = list(set(merged_fields[field]))

        # Combine summaries
        summaries = [r.get("partial_summary", "") for r in batch_results if r.get("partial_summary")]
        combined_summary = " ".join(summaries)

        return {
            "fields": merged_fields,
            "summary": combined_summary or "Analysis completed successfully."
        }


# Need to import Path
from pathlib import Path