# sentinel/run.py
import asyncio
import argparse
import logging
import signal
import os

from sentinel.supervisor import Supervisor
from sentinel import config

# Logger setup is handled in supervisor.py, but run.py can also use it.
logger = logging.getLogger("sentinel.run")

async def main(args):
    """Main function to initialize and run the Supervisor."""
    supervisor = None # Initialize to None for finally block
    try:
        supervisor = Supervisor(is_raw_enabled=args.raw)
    except ValueError as e:
        logger.critical(f"Failed to initialize Supervisor: {e}. Ensure INFLUXDB_TOKEN_LOCAL is set.")
        return # Exit if supervisor cannot be initialized
    
    # Handle graceful shutdown on SIGINT and SIGTERM
    loop = asyncio.get_event_loop()
    
    def signal_handler():
        logger.info("Signal received, initiating graceful shutdown...")
        asyncio.create_task(supervisor.stop()) # Schedule stop without blocking handler

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            # Windows does not support add_signal_handler for SIGINT/SIGTERM in the same way
            # For Windows, KeyboardInterrupt is the primary way to stop for SIGINT.
            # SIGTERM might need other platform-specific handling if strictly required.
            logger.warning(f"Signal handler for {sig.name} could not be set (likely on Windows).")
            pass

    duration = None
    if args.dry_run:
        logger.info("Executing DRAGON dry run... I mean DRY RUN.")
        duration = config.RUN_DURATION_SECONDS_DRY_RUN
        # In a true dry run, we might also redirect InfluxWriter to a mock or stdout.
        # For now, it will run for a short duration.
    elif args.live:
        logger.info("Executing LIVE run... Strap in!")
        duration = config.RUN_DURATION_SECONDS_LIVE # 48 hours as per plan
    else:
        # Default to a short dry run if no mode is specified
        logger.info("No run mode specified, defaulting to a short dry run.")
        duration = config.RUN_DURATION_SECONDS_DRY_RUN

    try:
        await supervisor.start(duration_seconds=duration)
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received by run.py. Supervisor should handle shutdown.")
        # Supervisor's signal handler or its own KeyboardInterrupt handling should manage this.
        # If supervisor.start() is still running, it will eventually call supervisor.stop()
        # or the signal handler will.
    except Exception as e:
        logger.exception(f"Unhandled exception in run.py main loop: {e}")
    finally:
        logger.info("Run.py main function cleanup starting...")
        if supervisor and not supervisor.stop_event.is_set():
            logger.info("Ensuring supervisor is stopped in finally block.")
            # This call is a safeguard. Ideally, supervisor.start or signal handler manages stop.
            await supervisor.stop() 
        logger.info("Run.py main function finished.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sentinel: BTC Order Book and Trade Recorder.")
    group = parser.add_mutually_exclusive_group() # Allow either --dry-run or --live, but not both
    group.add_argument("--dry-run", action="store_true", help="Run for a short duration (30s) and print logs.")
    group.add_argument("--live", action="store_true", help="Run continuously for the configured duration (e.g., 48h).")
    parser.add_argument("--raw", action="store_true", help="Enable collection and writing of raw top-N order book data to a separate bucket.")

    args = parser.parse_args()

    # Ensure INFLUXDB_TOKEN_LOCAL is available before trying to run
    if not os.getenv("INFLUXDB_TOKEN_LOCAL"):
        print("CRITICAL: INFLUXDB_TOKEN_LOCAL environment variable is not set. Sentinel cannot run.")
        print("Please set this environment variable with your local InfluxDB token.")
    else:
        try:
            asyncio.run(main(args))
        except KeyboardInterrupt:
            logger.info("Application terminated by KeyboardInterrupt at the top level.")
        except Exception as e:
            logger.critical(f"Top-level unhandled exception: {e}", exc_info=True) 