class ApiError(Exception):
    def __init__(self, message, error_code="ERROR", status=400):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.status = status
