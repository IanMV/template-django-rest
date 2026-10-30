from rest_framework.exceptions import APIException

from core.response_messages import MSG_SERVICE_UNAVAILABLE


class ServiceUnavailable(APIException):
    status_code = 503
    default_detail = MSG_SERVICE_UNAVAILABLE
