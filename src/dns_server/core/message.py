"""
DNS Message Parser Module

This module implements RFC 1035 compliant DNS message handling including:
- DNS header parsing/construction
- Question section handling
- Answer/Authority/Additional sections
- Support for all required record types (A, AAAA, CNAME, MX, NS, PTR, TXT, SOA)
"""

import logging
import socket
import struct
from dataclasses import dataclass
from enum import IntEnum
from typing import Dict, List, Tuple, Union

logger = logging.getLogger(__name__)


class DNSOpcode(IntEnum):
    """DNS Operation Codes"""

    QUERY = 0
    IQUERY = 1
    STATUS = 2
    NOTIFY = 4
    UPDATE = 5


class DNSResponseCode(IntEnum):
    """DNS Response Codes"""

    NOERROR = 0
    FORMERR = 1
    SERVFAIL = 2
    NXDOMAIN = 3
    NOTIMP = 4
    REFUSED = 5
    YXDOMAIN = 6
    YXRRSET = 7
    NXRRSET = 8
    NOTAUTH = 9
    NOTZONE = 10


class DNSRecordType(IntEnum):
    """DNS Record Types"""

    A = 1
    NS = 2
    CNAME = 5
    SOA = 6
    PTR = 12
    MX = 15
    TXT = 16
    AAAA = 28
    SRV = 33
    ANY = 255


class DNSClass(IntEnum):
    """DNS Classes"""

    IN = 1
    CS = 2
    CH = 3
    HS = 4
    ANY = 255


@dataclass
class DNSHeader:
    """DNS Message Header"""

    transaction_id: int
    flags: int
    question_count: int = 0
    answer_count: int = 0
    authority_count: int = 0
    additional_count: int = 0

    # Flag field components
    qr: bool = False  # Query/Response bit
    opcode: int = 0  # Operation code
    aa: bool = False  # Authoritative Answer
    tc: bool = False  # Truncation
    rd: bool = True  # Recursion Desired
    ra: bool = False  # Recursion Available
    z: int = 0  # Reserved (must be zero)
    rcode: int = 0  # Response code

    def __post_init__(self):
        """Update flags based on individual flag components"""
        self.flags = (
            (int(self.qr) << 15)
            | (self.opcode << 11)
            | (int(self.aa) << 10)
            | (int(self.tc) << 9)
            | (int(self.rd) << 8)
            | (int(self.ra) << 7)
            | (self.z << 4)
            | self.rcode
        )

    @classmethod
    def parse_flags(cls, flags: int) -> Dict[str, Union[bool, int]]:
        """Parse flags field into individual components"""
        return {
            "qr": bool(flags & 0x8000),
            "opcode": (flags >> 11) & 0x0F,
            "aa": bool(flags & 0x0400),
            "tc": bool(flags & 0x0200),
            "rd": bool(flags & 0x0100),
            "ra": bool(flags & 0x0080),
            "z": (flags >> 4) & 0x07,
            "rcode": flags & 0x0F,
        }

    def to_bytes(self) -> bytes:
        """Convert header to bytes"""
        return struct.pack(
            "!HHHHHH",
            self.transaction_id,
            self.flags,
            self.question_count,
            self.answer_count,
            self.authority_count,
            self.additional_count,
        )

    @classmethod
    def from_bytes(cls, data: bytes) -> "DNSHeader":
        """Parse header from bytes"""
        if len(data) < 12:
            raise ValueError("Invalid DNS header: too short")

        tid, flags, qcount, acount, authcount, addcount = struct.unpack(
            "!HHHHHH", data[:12]
        )

        flag_components = cls.parse_flags(flags)

        return cls(
            transaction_id=tid,
            flags=flags,
            question_count=qcount,
            answer_count=acount,
            authority_count=authcount,
            additional_count=addcount,
            **flag_components,
        )


@dataclass
class DNSQuestion:
    """DNS Question Section"""

    name: str
    qtype: int
    qclass: int

    def to_bytes(self) -> bytes:
        """Convert question to bytes"""
        name_bytes = self._encode_name(self.name)
        return name_bytes + struct.pack("!HH", self.qtype, self.qclass)

    def _encode_name(self, name: str) -> bytes:
        """Encode domain name using DNS label encoding"""
        if name == ".":
            return b"\x00"

        labels = name.rstrip(".").split(".")
        result = b""
        for label in labels:
            label_bytes = label.encode("ascii")
            if len(label_bytes) > 63:
                raise ValueError(f"Label too long: {label}")
            result += struct.pack("!B", len(label_bytes)) + label_bytes
        result += b"\x00"  # Root label
        return result

    @classmethod
    def parse(cls, data: bytes, offset: int) -> Tuple["DNSQuestion", int]:
        """Parse question from bytes at given offset"""
        name, new_offset = cls._decode_name(data, offset)
        if new_offset + 4 > len(data):
            raise ValueError("Invalid question: not enough data for type and class")

        qtype, qclass = struct.unpack("!HH", data[new_offset : new_offset + 4])
        return cls(name=name, qtype=qtype, qclass=qclass), new_offset + 4

    @staticmethod
    def _decode_name(data: bytes, offset: int) -> Tuple[str, int]:
        """Decode DNS name with compression support"""
        labels = []
        original_offset = offset
        jumped = False

        while True:
            if offset >= len(data):
                raise ValueError("Invalid name: offset out of bounds")

            length = data[offset]

            if length == 0:
                # End of name
                offset += 1
                break
            elif (length & 0xC0) == 0xC0:
                # Name compression
                if offset + 1 >= len(data):
                    raise ValueError("Invalid compression pointer")
                pointer = ((length & 0x3F) << 8) | data[offset + 1]
                if not jumped:
                    original_offset = offset + 2
                    jumped = True
                offset = pointer
            else:
                # Regular label
                if offset + length + 1 > len(data):
                    raise ValueError("Invalid label: length exceeds data")
                label = data[offset + 1 : offset + 1 + length].decode("ascii")
                labels.append(label)
                offset += length + 1

        name = ".".join(labels) + "." if labels else "."
        return name, original_offset if jumped else offset


@dataclass
class DNSResourceRecord:
    """DNS Resource Record"""

    name: str
    rtype: int
    rclass: int
    ttl: int
    rdata: bytes

    def to_bytes(self) -> bytes:
        """Convert resource record to bytes"""
        name_bytes = DNSQuestion._encode_name(None, self.name)
        header = struct.pack(
            "!HHIH", self.rtype, self.rclass, self.ttl, len(self.rdata)
        )
        return name_bytes + header + self.rdata

    @classmethod
    def parse(cls, data: bytes, offset: int) -> Tuple["DNSResourceRecord", int]:
        """Parse resource record from bytes at given offset"""
        name, new_offset = DNSQuestion._decode_name(data, offset)

        if new_offset + 10 > len(data):
            raise ValueError("Invalid resource record: not enough data for header")

        rtype, rclass, ttl, rdlength = struct.unpack(
            "!HHIH", data[new_offset : new_offset + 10]
        )
        new_offset += 10

        if new_offset + rdlength > len(data):
            raise ValueError("Invalid resource record: not enough data for rdata")

        rdata = data[new_offset : new_offset + rdlength]

        return (
            cls(name=name, rtype=rtype, rclass=rclass, ttl=ttl, rdata=rdata),
            new_offset + rdlength,
        )

    def get_readable_rdata(self) -> str:
        """Get human-readable representation of rdata"""
        try:
            if self.rtype == DNSRecordType.A:
                return socket.inet_ntoa(self.rdata)
            elif self.rtype == DNSRecordType.AAAA:
                return socket.inet_ntop(socket.AF_INET6, self.rdata)
            elif (
                self.rtype == DNSRecordType.CNAME
                or self.rtype == DNSRecordType.NS
                or self.rtype == DNSRecordType.PTR
            ):
                name, _ = DNSQuestion._decode_name(self.rdata + b"\x00", 0)
                return name
            elif self.rtype == DNSRecordType.MX:
                priority = struct.unpack("!H", self.rdata[:2])[0]
                name, _ = DNSQuestion._decode_name(self.rdata[2:] + b"\x00", 0)
                return f"{priority} {name}"
            elif self.rtype == DNSRecordType.TXT:
                # TXT records can have multiple strings
                strings = []
                offset = 0
                while offset < len(self.rdata):
                    length = self.rdata[offset]
                    if offset + length + 1 > len(self.rdata):
                        break
                    strings.append(
                        self.rdata[offset + 1 : offset + 1 + length].decode(
                            "utf-8", errors="replace"
                        )
                    )
                    offset += length + 1
                return '"' + '" "'.join(strings) + '"'
            elif self.rtype == DNSRecordType.SOA:
                # Parse SOA record
                mname, offset = DNSQuestion._decode_name(self.rdata + b"\x00", 0)
                rname, offset = DNSQuestion._decode_name(self.rdata + b"\x00", offset)
                serial, refresh, retry, expire, minimum = struct.unpack(
                    "!IIIII", self.rdata[offset : offset + 20]
                )
                return f"{mname} {rname} {serial} {refresh} {retry} {expire} {minimum}"
            else:
                return self.rdata.hex()
        except Exception as e:
            logger.warning(f"Failed to parse rdata for type {self.rtype}: {e}")
            return self.rdata.hex()


@dataclass
class DNSMessage:
    """Complete DNS Message"""

    header: DNSHeader
    questions: List[DNSQuestion]
    answers: List[DNSResourceRecord]
    authority: List[DNSResourceRecord]
    additional: List[DNSResourceRecord]

    def to_bytes(self) -> bytes:
        """Convert entire message to bytes"""
        # Update counts in header
        self.header.question_count = len(self.questions)
        self.header.answer_count = len(self.answers)
        self.header.authority_count = len(self.authority)
        self.header.additional_count = len(self.additional)

        result = self.header.to_bytes()

        for question in self.questions:
            result += question.to_bytes()

        for answer in self.answers:
            result += answer.to_bytes()

        for auth in self.authority:
            result += auth.to_bytes()

        for add in self.additional:
            result += add.to_bytes()

        return result

    @classmethod
    def from_bytes(cls, data: bytes) -> "DNSMessage":
        """Parse complete DNS message from bytes"""
        if len(data) < 12:
            raise ValueError("Invalid DNS message: too short")

        header = DNSHeader.from_bytes(data)
        offset = 12

        # Parse questions
        questions = []
        for _ in range(header.question_count):
            question, offset = DNSQuestion.parse(data, offset)
            questions.append(question)

        # Parse answers
        answers = []
        for _ in range(header.answer_count):
            answer, offset = DNSResourceRecord.parse(data, offset)
            answers.append(answer)

        # Parse authority records
        authority = []
        for _ in range(header.authority_count):
            auth, offset = DNSResourceRecord.parse(data, offset)
            authority.append(auth)

        # Parse additional records
        additional = []
        for _ in range(header.additional_count):
            add, offset = DNSResourceRecord.parse(data, offset)
            additional.append(add)

        return cls(
            header=header,
            questions=questions,
            answers=answers,
            authority=authority,
            additional=additional,
        )

    def is_query(self) -> bool:
        """Check if this is a query message"""
        return not self.header.qr

    def is_response(self) -> bool:
        """Check if this is a response message"""
        return self.header.qr

    def create_response(self, rcode: int = DNSResponseCode.NOERROR) -> "DNSMessage":
        """Create a response message based on this query"""
        response_header = DNSHeader(
            transaction_id=self.header.transaction_id,
            flags=0,
            qr=True,
            opcode=self.header.opcode,
            aa=False,
            tc=False,
            rd=self.header.rd,
            ra=True,
            z=0,
            rcode=rcode,
        )

        return DNSMessage(
            header=response_header,
            questions=self.questions.copy(),
            answers=[],
            authority=[],
            additional=[],
        )


def create_a_record(name: str, ip: str, ttl: int = 300) -> DNSResourceRecord:
    """Create an A record"""
    rdata = socket.inet_aton(ip)
    return DNSResourceRecord(
        name=name, rtype=DNSRecordType.A, rclass=DNSClass.IN, ttl=ttl, rdata=rdata
    )


def create_aaaa_record(name: str, ip: str, ttl: int = 300) -> DNSResourceRecord:
    """Create an AAAA record"""
    rdata = socket.inet_pton(socket.AF_INET6, ip)
    return DNSResourceRecord(
        name=name, rtype=DNSRecordType.AAAA, rclass=DNSClass.IN, ttl=ttl, rdata=rdata
    )


def create_cname_record(name: str, target: str, ttl: int = 300) -> DNSResourceRecord:
    """Create a CNAME record"""
    rdata = DNSQuestion._encode_name(None, target)
    return DNSResourceRecord(
        name=name, rtype=DNSRecordType.CNAME, rclass=DNSClass.IN, ttl=ttl, rdata=rdata
    )


def create_mx_record(
    name: str, priority: int, target: str, ttl: int = 300
) -> DNSResourceRecord:
    """Create an MX record"""
    rdata = struct.pack("!H", priority) + DNSQuestion._encode_name(None, target)
    return DNSResourceRecord(
        name=name, rtype=DNSRecordType.MX, rclass=DNSClass.IN, ttl=ttl, rdata=rdata
    )


def create_txt_record(name: str, text: str, ttl: int = 300) -> DNSResourceRecord:
    """Create a TXT record"""
    # Split text into 255-byte chunks if necessary
    text_bytes = text.encode("utf-8")
    rdata = b""

    offset = 0
    while offset < len(text_bytes):
        chunk = text_bytes[offset : offset + 255]
        rdata += struct.pack("!B", len(chunk)) + chunk
        offset += 255

    return DNSResourceRecord(
        name=name, rtype=DNSRecordType.TXT, rclass=DNSClass.IN, ttl=ttl, rdata=rdata
    )
