#!/usr/bin/env python3

import argparse
import logging
import sys
import threading
import time
from traceback import print_exc

from lucido.core import (ProtocolEngine, MsgpackSerialiser, FunctionRegister, OutgoingRequest, RequestCallbackInfo, JsonSerialiser, IncomingResponse, IncomingException,
                       OutgoingLinkedMessage, FinalType, CalleeException, CallerException, make_export_decorator)
from lucido.threaded import TcpConnector, ThreadPoolDispatcher


logging.basicConfig(stream=sys.stdout, level=logging.INFO, format='[%(asctime)s] {%(filename)s:%(lineno)d} %(levelname)s - %(message)s')


export = make_export_decorator()

@export
def display_chat_message(msg):
    print('********** Got incoming message **********')
    print(msg)                    
    print('**************************************')
    print()


def show_progress(message):
    print(f'Running callback in {threading.current_thread().name}')
    print(message)
    print('--------------')


def show_data(data):
    print(f'Got data: {data}')


class ResultWaiter:
    def __init__(self):
        self.got_result = threading.Event()
        self.messages = []
        self.result = None
        self.exception = None

    def process_msg(self, msg):
        show_data(msg)
        if isinstance(msg, IncomingResponse):
            self.result = msg.result
            self.got_result.set()
        elif isinstance(msg, IncomingException):
            self.exception = msg.exc_info
            self.got_result.set()
        else:
            self.messages.append(msg)

    def get_result(self):
        self.got_result.wait()
        if self.exception:
            raise RuntimeError('Something bad happended')
        else:
            return self.result


def background_counter(channel, count_to, delay):
    print(f'*** Calling slow counter in background thread {threading.current_thread().name}')

    cb = lambda message: print(f'*** Got msg: {message}. Displaying in thread {threading.current_thread().name}')
    result = channel.request.slow_counter(count_to=count_to, delay=delay, progress=cb)

    print(f'*** Background counter result: {result}')


def main(use_msgpack):
    if use_msgpack:
        serialiser = MsgpackSerialiser()
    else:
        serialiser = JsonSerialiser()
    engine = ProtocolEngine(serialiser)
    dispatcher = ThreadPoolDispatcher(num_threads=5)
    connector = TcpConnector(engine, dispatcher)
    channel = connector.connect('127.0.0.1', 5000)
    channel.start_channel()

    # start of test calls

    result = channel.request(namespace='#sys').ping()
    print(f'Ping result: {result}')

    result = channel.request.hello_world()
    print(result)

    result = channel.request.hello_world(name='Bill')
    print(result)

    print()
    print('Requesting send and ack callbacks...')
    ack_requester = channel.request(msg_sent_callback=show_data, ack_callback=show_data)
    result = ack_requester.hello_world()
    print(f'Got result: {result}')

    print('Calling slow counter...')
    result = channel.request.slow_counter(count_to=5, progress=show_progress)
    print(f'Got result: {result}')

    background_thread = threading.Thread(target=background_counter, args=(channel, 5, 1))
    background_thread.start()

    print('Sleeping 2 on the main thread')
    time.sleep(2)

    print('Multipart response (returns a generator)')
    for x in channel.request(multipart_reponse=True).multipart_response(count_to=10):
        print(x)
    print('Multipart response complete.')

    print('Sleeping 2 on the main thread')
    time.sleep(2)

    print('Iterable param (IterableCallback) - Pull')
    iter_data = iter([1, 2, 3, 4])
    result = channel.request.iterable_param(nums=iter_data)
    print(f'Got result: {result}')

    # # probably remove multipart requests and just use streaming (multipart) iterable callbacks instead.
    # proxy = channel.get_proxy()
    # print('Calling multipart request')
    # req = OutgoingRequest('multipart_request', params={'start': 100})
    # result_watier = ResultWaiter()
    # req_id = proxy.send_request_raw_async(req, result_watier.process_msg)
    # for item in [10, 15, 15, 20]:
    #     print(f'Sending {item}')
    #     proxy.send_linked_message(OutgoingLinkedMessage(req_id, item))
    # proxy.send_linked_message(OutgoingLinkedMessage(req_id, final=FinalType.TERMINATOR))
    # result = result_watier.get_result()
    # print(f'Got result: {result}')

    # print('Sleeping 2 on the main thread')
    # time.sleep(2)

    print('Waiting for backgroud thread')
    background_thread.join()

    # for (a, b) in [(1, 2), (1, 0), (3, 4), (11, 22), (None, 2), ('a', 'b')]:
    #     try:
    #         print()
    #         print(f'Calling division with a = {a}, b = {b}')
    #         result = channel.request.division(a=a, b=b)
    #         print(f'Got result: {result}')
    #     except CallerException as e:
    #         print(f'Opps - we made a mistake: {str(e)}')
    #     except CalleeException as e:
    #         print(f'Opps - something went wrong at the other end. {str(e)}')
    #     except Exception as e:
    #         print(f'Some other error - {str(e)}')

    channel.shutdown_channel()
    dispatcher.shutdown()

    print('Done')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--debug', action='store_true')
    parser.add_argument('--msgpack', action='store_true')
    args = parser.parse_args()

    root_logger = logging.getLogger()
    if args.debug:
        root_logger.setLevel(logging.DEBUG)
    main(args.msgpack)
