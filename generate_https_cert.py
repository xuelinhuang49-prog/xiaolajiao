
from pathlib import Path
from datetime import datetime, timedelta, timezone
import ipaddress

from cryptography import x509
from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import hashes, serialization

CERT_DIR = Path(__file__).resolve().parent / "https_certs"
CERT_DIR.mkdir(exist_ok=True)

IP = "192.168.1.103"
now = datetime.now(timezone.utc)

# 创建本地测试 CA
ca_key = rsa.generate_private_key(
    public_exponent=65537,
    key_size=3072
)

ca_name = x509.Name([
    x509.NameAttribute(NameOID.COMMON_NAME, "XiaoLaJiao Local Test CA")
])

ca_cert = (
    x509.CertificateBuilder()
    .subject_name(ca_name)
    .issuer_name(ca_name)
    .public_key(ca_key.public_key())
    .serial_number(x509.random_serial_number())
    .not_valid_before(now - timedelta(days=1))
    .not_valid_after(now + timedelta(days=365))
    .add_extension(
        x509.BasicConstraints(ca=True, path_length=0),
        critical=True
    )
    .add_extension(
        x509.KeyUsage(
            digital_signature=True,
            content_commitment=False,
            key_encipherment=False,
            data_encipherment=False,
            key_agreement=False,
            key_cert_sign=True,
            crl_sign=True,
            encipher_only=False,
            decipher_only=False
        ),
        critical=True
    )
    .sign(ca_key, hashes.SHA256())
)

# 创建 HTTPS 服务器证书
server_key = rsa.generate_private_key(
    public_exponent=65537,
    key_size=2048
)

server_name = x509.Name([
    x509.NameAttribute(NameOID.COMMON_NAME, IP)
])

server_cert = (
    x509.CertificateBuilder()
    .subject_name(server_name)
    .issuer_name(ca_name)
    .public_key(server_key.public_key())
    .serial_number(x509.random_serial_number())
    .not_valid_before(now - timedelta(days=1))
    .not_valid_after(now + timedelta(days=90))
    .add_extension(
        x509.BasicConstraints(ca=False, path_length=None),
        critical=True
    )
    .add_extension(
        x509.SubjectAlternativeName([
            x509.IPAddress(ipaddress.ip_address(IP)),
            x509.DNSName("localhost")
        ]),
        critical=False
    )
    .add_extension(
        x509.ExtendedKeyUsage([
            ExtendedKeyUsageOID.SERVER_AUTH
        ]),
        critical=False
    )
    .sign(ca_key, hashes.SHA256())
)

def save_cert(filename, cert):
    (CERT_DIR / filename).write_bytes(
        cert.public_bytes(serialization.Encoding.PEM)
    )

def save_key(filename, key):
    (CERT_DIR / filename).write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption()
        )
    )

save_cert("xiaolajiao_ca.crt", ca_cert)
save_cert("server.crt", server_cert)
save_key("server.key", server_key)
save_key("ca.key", ca_key)

print("HTTPS 证书生成成功！")
print("证书目录：", CERT_DIR)
print("服务器 IP：", IP)
print("注意：ca.key 和 server.key 必须保密")
