import asyncio
import calendar
import datetime
import json
import os
import time
import traceback

from async_timeout import timeout
from azure.identity.aio import DefaultAzureCredential
from azure.servicebus import ServiceBusMessage
from azure.servicebus.aio import ServiceBusClient

from common.common_utils import logger
from common.config import Config
from common.logfile_uploader import upload_logfiles


class Service:
    def __init__(
        self,
        task,
        message_batch_size,
        _timeout,
        in_queue=os.environ["APP_SERVICE_IN_QUEUE"],
        out_queue=os.environ["APP_SERVICE_OUT_QUEUE"],
    ):
        self.fully_qualified_namespace = os.environ["APP_SB_FULLY_QUALIFIED_NAMESPACE"]
        self.in_queue_name = in_queue
        self.out_queue_name = out_queue
        self.command_queue_name = os.environ["APP_SERVICE_COMMAND_QUEUE"]
        self.sleep_seconds = 4
        self.total_sent = 0
        self.total_rec = 0
        self.last_processed_time = 0
        self.last_upload_time = 0
        self.last_scheduled_time = 0
        self.num_upload = 0
        self.start_time = time.time()
        self.message_sent_today = False
        self.today_upload_status = False
        self.sequence_number = None
        self.task = task
        self.processed_messages = 0
        self.total_processed_messages = 0
        self._timeout = _timeout
        self.message_batch_size = message_batch_size
        self.today_upload_status = None
        self.last_upload_date = None
        self.process = None
        self.last_scheduled_date = None
        self.retrieving_message = "Retrieving default credential..."
        self.creating_bus_message = "Message to be scheduled"

    async def send_single_message(self, sender, message):
        """Function to send a single message"""
        await sender.send_messages(ServiceBusMessage(message))
        logger.info("Single message sent")

    async def send_scheduled_message(self):
        """
        Function sends a scheduled message using Azure Service Bus.
        Args:
            sb_namespace_fq: fully qualified namespace

        Returns:
            target_datetime: target upload datetime generated from configuration file
            sequence_number: sequence number for scheduled message
        """

        # generate target schedule datetime
        now = datetime.datetime.utcnow()
        target_time = datetime.datetime.strptime(
            Config.LOG_TARGET_UPLOAD_TIME, "%H:%M:%S"
        ).time()
        target_datetime = datetime.datetime.combine(now.date(), target_time)
        self.last_scheduled_date = datetime.datetime.utcfromtimestamp(
            self.last_scheduled_time
        ).date()

        # If a new day has started, the message_sent_today variable is reset and the sequence number is set to None.
        if (now.date() - self.last_scheduled_date) >= datetime.timedelta(days=1):
            logger.info("No scheduled message to be sent.")
            self.message_sent_today = False
            self.sequence_number = None
        # If the current time is less than the target time and a message has not been sent today, a message is scheduled.
        if (
            now < target_datetime
            and not self.message_sent_today
            and (time.time() - self.last_scheduled_time) > 86400
        ):
            try:
                logger.info(f"Connecting to command queue : {self.command_queue_name}")
                logger.info(self.retrieving_message)
                credential = DefaultAzureCredential()
                
                logger.info(self.creating_bus_message)
                sb_client = ServiceBusClient(
                    fully_qualified_namespace=self.fully_qualified_namespace,
                    credential=credential,
                    logging_enable=True,
                )
                
                async with sb_client:
                    sender = sb_client.get_queue_sender(self.command_queue_name)
                    async with sender:
                        # send scheduled message
                        message = ServiceBusMessage("Message to be scheduled")
                        self.sequence_number = await sender.schedule_messages(
                            message, target_datetime
                        )
                        logger.info(
                            f"Scheduled message sent with sequence number: {self.sequence_number}, scheduled datetime: {target_datetime}"
                            )
                        self.last_scheduled_time = int(time.time())
                        self.message_sent_today = True
                sender.close()
                sb_client.close()
                credential.close()
            except Exception as e:
                logger.warning(
                    f"Error sending scheduled message: {e}"
                    )
        return target_datetime

    async def receive_scheduled_message(self, target_datetime: datetime):
        """
        Function to receive scheduled messages and execute log file upload action
        Args:
            sb_namespace_fq: fully qualified namespace of the Service Bus
            target_datetime: Target datetime to receive the message
            sequence_number: Sequence number of the message

        Returns:
            today_upload_status: upload status either True or False
            last_upload_time: last upload time
        """

        target_datetime = int(calendar.timegm(target_datetime.utctimetuple()))

        now = datetime.datetime.utcnow()
        self.last_upload_date = datetime.datetime.utcfromtimestamp(
            self.last_upload_time
        ).date()

        # If it's been more than a day since the last upload, reset the upload status and attempt count
        if (now.date() - self.last_upload_date) >= datetime.timedelta(days=1):
            self.today_upload_status = False
            upload_attempt = 0

        try:
            # If a sequence number is provided and the current time is past the target datetime
            if (self.sequence_number is not None) & (
                int(time.time()) > target_datetime
            ):
                while not self.today_upload_status:
                    logger.info(self.retrieving_message)
                    credential = DefaultAzureCredential()
                    
                    logger.info(self.creating_bus_message)
                    sb_client = ServiceBusClient(
                        fully_qualified_namespace=self.fully_qualified_namespace,
                        credential=credential,
                        logging_enable=True,
                    )
                    
                    async with sb_client:
                        receiver = sb_client.get_queue_receiver(self.command_queue_name)
                        async with receiver:
                            received_msgs = await receiver.receive_messages(
                                max_wait_time=3, max_message_count=1
                            )
                            # If a message was received, attempt to upload log files
                            if len(received_msgs) > 0:
                                self.today_upload_status = upload_logfiles()
                                self.last_upload_time = int(time.time())
                        
                    receiver.close()
                    sb_client.close()
                    credential.close()
                    
                    # increment the upload attempt count
                    upload_attempt += 1                    
                    # If more than 20 attempts have been made, stop trying for the day
                    if upload_attempt > 20:
                        self.last_upload_time = int(time.time())
                        self.today_upload_status = True
                        logger.warning(
                            "Max upload attempts reached, breaking out of upload loop"
                            )
        except Exception as e:
            logger.warning(
                f"Error receiving scheduled message: {e}"
                )
            
    async def setup_worker(self, data):
        while True:
            self.processed_messages = 0
            try:
                await self.process_task(data)
            except TimeoutError:
                logger.warning(
                    f"perform_task operation timed out after {self._timeout} seconds..."
                )
            except Exception as e:
                logger.warning(f"During perform_task error `{e}` occurred.")

            if self.processed_messages > 0:
                self.sleep_seconds = 1
            else:
                if self.sleep_seconds < 10:
                    self.sleep_seconds += 1

            logger.info(
                f"{self.processed_messages} messages processed in this batch -> sleep for {self.sleep_seconds} seconds"
            )
            self.processed_messages = 0
            logger.info(
                f"{self.total_processed_messages} messages processed since the start of the service"
            )

            target_datetime = await self.send_scheduled_message()
            await self.receive_scheduled_message(target_datetime)

            await asyncio.sleep(self.sleep_seconds)

    async def process_message(self, raw_message, data):
        try:
            load = json.loads(raw_message)
            
            logger.info(
                f"Received id: {load['id']}, size: {len(raw_message)} total received: {self.total_rec}"
            )
            perf_start_time = time.perf_counter()
            async with timeout(self._timeout):
                result = self.task.produce_result(
                    load, data
                ) # perform the core business logic
                logger.info(
                    f"Main processing completed within {time.perf_counter() - perf_start_time:0.3f} seconds."
                )
                
                try:
                    logger.info(self.retrieving_message)
                    credential = DefaultAzureCredential()
                    
                    logger.info(self.creating_bus_message)
                    sb_client = ServiceBusClient(
                        fully_qualified_namespace=self.fully_qualified_namespace,
                        credential=credential,
                        logging_enable=True,
                    )
                    
                    logger.info(
                        f"Sending result to output queue {self.out_queue_name} total sent: {self.total_sent}"
                    )
                    async with sb_client:
                        perf_start_time = time.perf_counter()
                        sender = sb_client.get_queue_sender(self.out_queue_name)
                        async with sender:
                            await self.send_single_message(
                                sender, str(json.dumps(result))
                            )
                        self.total_sent += 1
                        logger.info(
                            f"Result sent within {time.perf_counter() - perf_start_time:0.3f} seconds."
                        )
                except Exception as ex:
                    traceback.print_exc()
                    logger.warning(
                        f"Exception in sending response to output queue. Exception of type: {type(ex).__name__}"
                    )
                    await sender.close()
                    await sb_client.close()
                    await credential.close()
                    
        except Exception as ex:
            traceback.print_exc()
            logger.warning(
                f"Exception in process_message. Exception of type: {type(ex).__name__}"
            )

async def process_task(self, data):
    try:
        logger.info(self.retrieving_message)
        credential = DefaultAzureCredential()

        logger.info(self.creating_bus_message)
        servicebus_client = ServiceBusClient(
            fully_qualified_namespace=self.fully_qualified_namespace,
            credential=credential,
            logging_enable=True,
        )

        async with servicebus_client:
            logger.info(f"Connecting to input queue: {self.in_queue_name}")
            receiver = servicebus_client.get_queue_receiver(
                self.in_queue_name
                )
            async with receiver:
                received_msgs = await receiver.receive_messages(
                    max_wait_time=3, max_message_count=self.message_batch_size
                    )
                if len(received_msgs) < 1:
                    logger.info(f"No messages to process.")
                else:
                    logger.info(f"Messages to process: {len(received_msgs)}")
                    for index, msg in enumerate(received_msgs):
                        raw_message = str(msg)

                        try:
                            await receiver.complete_message(
                                msg
                                )
                            # remove the message from the queue
                        except Exception as e:
                            logger.warning(
                                f"Error completing message: {e}"
                                )
                            self.sleep_seconds = 0
                        
                        self.processed_messages += 1
                        self.total_rec += 1
                        self.last_processed_time = int(time.time())

                        logger.info("Here is where the processing starts")

                        try:
                            await self.process_message(raw_message, data)
                        except Exception as e:
                            logger.warning(
                                f"Error processing message: {e}"
                                )
                            self.sleep_seconds = 0

            await receiver.close()
            await servicebus_client.close()
            await credential.close()

            self.total_processed_messages += self.processed_messages
            data["sleep_seconds"] = self.sleep_seconds
            data["total_sent"] = self.total_sent
            data["total_rec"] = self.total_rec
            data["last_processed_time"] = (
                time.strftime(
                    "%Y-%m-%d %H:%M:%S", time.localtime(self.last_processed_time)
                    ),
            )
            data["last_upload_time"] = self.last_upload_time
            data["last_scheduled_time"] = self.last_scheduled_time
            data["num_upload"] = self.num_upload
            data["start_time"] = time.strftime(
                "%Y-%m-%d %H:%M:%S", time.gmtime(self.start_time)
                )
            data["total_processed_messages"] = self.total_processed_messages

    except TimeoutError:
        logger.warning(
            f"process_task operation timed out after {self._timeout} seconds..."
            )
    except Exception as e:
        logger.warning(f"During process_task error `{e}` occurred.")
