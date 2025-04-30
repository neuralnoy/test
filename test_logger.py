from common.logger import get_logger

# Get loggers with different names to test the configuration
logger1 = get_logger("test_logger1")
logger2 = get_logger("test_logger2")

# Test different log levels
logger1.info("This is an info message from logger1")
logger1.warning("This is a warning message from logger1")
logger1.error("This is an error message from logger1")

logger2.info("This is an info message from logger2")
logger2.warning("This is a warning message from logger2")
logger2.error("This is an error message from logger2")

print("\nLog messages have been written to terminal and to the logs/app.log file.")
print("Check the file to see the consolidated logs.") 