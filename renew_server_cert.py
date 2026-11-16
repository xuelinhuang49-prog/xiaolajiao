
from pathlib import Path
from datetime import datetime, timedelta, timezone
import ipaddress

from cryptography import x509
from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import hashes, serialization

CERT_DIR = Path(__file__).resolve().parent / "https_certs"

# 新的电脑局域网 IP
IP = "192.168.1.103"

# 读取原来的 CA 证书和私钥，不重新生成
ca_cert = x509.load_pem_x509_certificate(
    (CERT_DIR / "xiaolajiao_ca.cer").read_bytes()
)
ca_key = serialization.load_pem_private_key(
    (CERT_DIR / "ca.key").read_bytes(),
    password=None
)

now = datetime.now(timezone.utc)

# 生成新的服务器私钥
server_key = rsa.generate_private_key(
    public_exponent=65537,
    key_size=2048
)

# 签发新服务器证书
server_cert = (
    x509.CertificateBuilder()
    .subject_name(x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, IP)
    ]))
    .issuer_name(ca_cert.subject)
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

(CERT_DIR / "server.crt").write_bytes(
    server_cert.public_bytes(serialization.Encoding.PEM)
)

(CERT_DIR / "server.key").write_bytes(
    server_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()
    )
)

print("服务器证书更新成功！")
print("新 IP：", IP)
print("原 CA 根证书保持不变")
