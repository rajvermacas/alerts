"""Test client for A2A servers.

This script demonstrates how to interact with the orchestrator
and insider trading agent servers via the A2A protocol.

Usage:
    # Test the orchestrator (default)
    python -m alerts.a2a.test_client

    # Test the insider trading agent directly
    python -m alerts.a2a.test_client --server-url http://localhost:10001

    # Specify a different alert file
    python -m alerts.a2a.test_client --alert test_data/alerts/alert_false_positive.xml
"""

import asyncio
import logging
from uuid import uuid4

import click
import httpx
from a2a.client import A2ACardResolver, A2AClient
from a2a.types import MessageSendParams, SendMessageRequest, SendStreamingMessageRequest

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_server(
    server_url: str,
    alert_path: str,
    use_streaming: bool = False,
) -> None:
    """Test an A2A server with an alert analysis request.

    Args:
        server_url: URL of the A2A server to test
        alert_path: Path to the alert file to analyze
        use_streaming: Whether to use streaming mode
    """
    logger.info(f"Testing A2A server at: {server_url}")
    logger.info(f"Alert file: {alert_path}")

    async with httpx.AsyncClient(timeout=300.0) as httpx_client:
        # Get agent card
        resolver = A2ACardResolver(
            httpx_client=httpx_client,
            base_url=server_url,
        )

        try:
            agent_card = await resolver.get_agent_card()
            logger.info("=" * 60)
            logger.info("AGENT CARD")
            logger.info("=" * 60)
            logger.info(f"Name: {agent_card.name}")
            logger.info(f"Description: {agent_card.description}")
            logger.info(f"Version: {agent_card.version}")
            logger.info(f"URL: {agent_card.url}")

            if agent_card.skills:
                logger.info("\nSkills:")
                for skill in agent_card.skills:
                    logger.info(f"  - {skill.name}: {skill.description}")
                    if skill.examples:
                        logger.info(f"    Examples: {skill.examples}")

            logger.info("=" * 60)

        except Exception as e:
            logger.error(f"Failed to get agent card: {e}")
            return

        # Create client
        client = A2AClient(httpx_client=httpx_client, agent_card=agent_card)

        # Create message
        message_payload = {
            "message": {
                "role": "user",
                "parts": [
                    {
                        "kind": "text",
                        "text": f"Analyze the alert at: {alert_path}",
                    }
                ],
                "messageId": uuid4().hex,
            },
        }

        if use_streaming:
            logger.info("\nSending streaming request...")
            request = SendStreamingMessageRequest(
                id=str(uuid4()),
                params=MessageSendParams(**message_payload),
            )

            try:
                stream_response = client.send_message_streaming(request)
                async for chunk in stream_response:
                    print(chunk.model_dump(mode="json", exclude_none=True))
            except Exception as e:
                logger.error(f"Streaming request failed: {e}")

        else:
            logger.info("\nSending request...")
            request = SendMessageRequest(
                id=str(uuid4()),
                params=MessageSendParams(**message_payload),
            )

            try:
                response = await client.send_message(request)
                logger.info("\n" + "=" * 60)
                logger.info("RESPONSE")
                logger.info("=" * 60)
                print(response.model_dump_json(indent=2, exclude_none=True))
            except Exception as e:
                logger.error(f"Request failed: {e}")


@click.command()
@click.option(
    "--server-url",
    default="http://localhost:10000",
    help="URL of the A2A server to test",
)
@click.option(
    "--alert",
    default="test_data/alerts/alert_genuine.xml",
    help="Path to the alert file to analyze",
)
@click.option(
    "--streaming",
    is_flag=True,
    help="Use streaming mode",
)
def main(server_url: str, alert: str, streaming: bool) -> None:
    """Test client for A2A servers."""
    asyncio.run(test_server(server_url, alert, streaming))


if __name__ == "__main__":
    main()
