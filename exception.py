class ErrorNotToSend(Exception):
    pass


class SendMessageFailed(ErrorNotToSend):
    pass


class EmptyResponse(ErrorNotToSend):
    pass


class UnexpectedHTTPStatusCodeError(Exception):
    pass


class UnexpectedTypeError(Exception):
    pass
