class PDFabricError(Exception):
    code: str = "PDFABRIC_ERROR"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class InvalidPDFError(PDFabricError):
    code = "INVALID_PDF"


class PageOutOfRangeError(PDFabricError):
    code = "PAGE_OUT_OF_RANGE"


class InvalidPageRangeError(PDFabricError):
    code = "INVALID_PAGE_RANGE"


class ConversionError(PDFabricError):
    code = "CONVERSION_ERROR"


class LibreOfficeNotFoundError(PDFabricError):
    code = "LIBREOFFICE_NOT_FOUND"


class UnsupportedFileTypeError(PDFabricError):
    code = "UNSUPPORTED_FILE_TYPE"
