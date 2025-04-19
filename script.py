#!./venv/bin/python

import os
import aiohttp
import asyncio
from aiohttp import ClientError
from urllib.parse import urlparse
from rich.progress import (
    Progress,
    TextColumn,
    BarColumn,
    TaskProgressColumn,
    TimeRemainingColumn,
)
from rich.console import Console


async def download_single_file(
    session, url, end_byte, output_path, custom_headers, progress, task_id
):
    """
    Downloads a single file with error handling using aiohttp.

    Args:
        session (aiohttp.ClientSession): The aiohttp session
        url (str): The URL of the file to download
        end_byte (int): Ending byte position
        output_path (str): Path where the file should be saved
        progress (rich.progress.Progress): Rich progress instance
        task_id (int): Task ID for progress tracking

    Returns:
        bool: True if download was successful, False otherwise
    """
    while True:
        try:
            # Determine start byte based on existing file size
            start_byte = 0
            if os.path.exists(output_path):
                start_byte = os.path.getsize(output_path)

            headers = {
                "Range": f"bytes={start_byte}-{end_byte}",
                **custom_headers,
            }

            async with session.get(url, headers=headers) as response:
                response.raise_for_status()

                # Create directory if it doesn't exist
                os.makedirs(os.path.dirname(output_path), exist_ok=True)

                # Calculate total size for progress bar
                downloaded = start_byte

                # Open file in append mode if it exists, write mode if it doesn't
                mode = "ab" if os.path.exists(output_path) else "wb"
                with open(output_path, mode) as f:
                    async for chunk in response.content.iter_chunked(
                        32768
                    ):  # 32KB chunks
                        f.write(chunk)
                        downloaded += len(chunk)
                        progress.update(task_id, completed=downloaded)

                return True

        except ClientError as e:
            continue
        except IOError as e:
            print(f"\nError writing file {output_path}: {str(e)}")
            return False
        except Exception as e:
            print(f"\nUnexpected error for {url}: {str(e)}")
            return False


async def download_multiple_files(urls_and_ranges, custom_headers=None):
    """
    Downloads multiple files concurrently using aiohttp.

    Args:
        urls_and_ranges (list of tuples): List of (url, end_byte) tuples

    Returns:
        list: List of booleans indicating success/failure for each download
    """
    if custom_headers is None:
        custom_headers = {}

    console = Console()
    progress = Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        console=console,
    )

    tasks = []

    async with aiohttp.ClientSession() as session:
        with progress:
            # Use a semaphore to limit concurrent downloads
            semaphore = asyncio.Semaphore(10)  # Allow 3 concurrent downloads

            async def download_with_semaphore(url, end_byte):
                async with semaphore:
                    # Generate output path from URL
                    parsed_url = urlparse(url)
                    filename = os.path.basename(parsed_url.path)
                    if not filename:
                        filename = "downloaded_file"
                    output_path = os.path.join("downloads", filename)

                    if (
                        os.path.exists(output_path)
                        and os.path.getsize(output_path) == end_byte
                    ):
                        print(
                            f"Skipping {output_path} because it already fully downloaded"
                        )
                        return

                    task_id = progress.add_task(
                        f"Downloading {filename}", total=end_byte
                    )
                    await download_single_file(
                        session,
                        url,
                        end_byte,
                        output_path,
                        custom_headers,
                        progress,
                        task_id,
                    )

            # Create tasks for all downloads
            tasks = [
                download_with_semaphore(url, end_byte)
                for url, end_byte in urls_and_ranges
            ]
            # Run all tasks concurrently, with semaphore limiting concurrency
            await asyncio.gather(*tasks)
