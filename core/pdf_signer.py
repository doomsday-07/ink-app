import os
from pathlib import Path
from PIL import Image
import fitz  # PyMuPDF


class PDFSigner:
    """Handles PDF viewing, signature placement, and cryptographic signing."""

    def __init__(self):
        self._doc: fitz.Document | None = None
        self._filepath: str | None = None

    def open_pdf(self, filepath: str) -> fitz.Document:
        """Open a PDF file for viewing/signing."""
        self._filepath = filepath
        self._doc = fitz.open(filepath)
        return self._doc

    def close(self):
        if self._doc:
            self._doc.close()
            self._doc = None
            self._filepath = None

    def get_page_count(self) -> int:
        if self._doc:
            return len(self._doc)
        return 0

    def get_page_pixmap(self, page_num: int, zoom: float = 2.0):
        """Render a page as a pixmap for display."""
        if not self._doc:
            return None
        page = self._doc[page_num]
        mat = fitz.Matrix(zoom, zoom)
        return page.get_pixmap(matrix=mat)

    def add_signature_image(
        self,
        page_num: int,
        signature_image_path: str,
        rect: tuple[float, float, float, float],
        opacity: float = 1.0,
    ) -> bool:
        """Place a signature image on a PDF page at the given rect (x0, y0, x1, y1)."""
        if not self._doc:
            return False
        page = self._doc[page_num]
        sig_rect = fitz.Rect(rect)
        page.insert_image(sig_rect, filename=signature_image_path, overlay=True)
        return True

    def add_ink_signature(
        self,
        page_num: int,
        points: list[list[tuple[float, float]]],
        color: tuple[float, float, float] = (0, 0, 0),
        width: float = 2.0,
    ) -> bool:
        """Add an ink annotation (freehand) signature on a PDF page."""
        if not self._doc:
            return False
        page = self._doc[page_num]
        ink_list = []
        for stroke in points:
            ink_list.append([fitz.Point(p) for p in stroke])
        annot = page.add_ink_annot(ink_list)
        annot.set_colors(stroke=color)
        annot.set_border(width=width)
        annot.update()
        return True

    def save_pdf(self, output_path: str):
        """Save the modified PDF."""
        if self._doc:
            self._doc.save(output_path)

    def save_pdf_incremental(self):
        """Save changes to the original file (incremental save)."""
        if self._doc and self._filepath:
            self._doc.save(self._filepath, incremental=True, encryption=0)

    def get_page_size(self, page_num: int) -> tuple[float, float]:
        """Get page width and height."""
        if not self._doc:
            return (0, 0)
        page = self._doc[page_num]
        rect = page.rect
        return (rect.width, rect.height)

    @staticmethod
    def generate_self_signed_cert(cert_dir: str) -> tuple[str, str]:
        """Generate a self-signed certificate for testing.
        Returns (cert_path, key_path)."""
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        import datetime

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, "InkApp Test Signer"),
        ])

        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.datetime.utcnow())
            .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=365))
            .sign(key, hashes.SHA256())
        )

        os.makedirs(cert_dir, exist_ok=True)
        cert_path = os.path.join(cert_dir, "signer_cert.pem")
        key_path = os.path.join(cert_dir, "signer_key.pem")

        with open(cert_path, "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))
        with open(key_path, "wb") as f:
            f.write(key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.TraditionalOpenSSL,
                serialization.NoEncryption(),
            ))

        return cert_path, key_path

    def sign_pdf(self, output_path: str, cert_path: str, key_path: str):
        """Apply a cryptographic signature using pyHanko."""
        from pyhanko.sign import signers
        from pyhanko.sign.fields import SigFieldSpec, append_signature_field
        from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
        from pyhanko.sign.signers.pdf_cms import Signer

        if not self._filepath:
            raise ValueError("No PDF file is open")

        signer = signers.SimpleSigner.load(cert_file=cert_path, key_file=key_path)

        with open(self._filepath, "rb") as f:
            w = IncrementalPdfFileWriter(f)

            append_signature_field(
                w,
                sig_field_spec=SigFieldSpec(
                    "Signature1",
                    on_page=0,
                    box=(100, 100, 300, 150),
                ),
            )

            meta = signers.PdfSignatureMetadata(
                field_name="Signature1",
            )
            pdf_signer = signers.PdfSigner(meta, signer=signer)

            with open(output_path, "wb") as out:
                pdf_signer.sign_pdf(w, output=out)
