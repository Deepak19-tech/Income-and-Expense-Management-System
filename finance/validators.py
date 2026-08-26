import re

from django.core.exceptions import ValidationError
from django.core.validators import validate_email


LOCAL_PART_RE = re.compile(r"^[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+)*$")
DOMAIN_LABEL_RE = re.compile(r'^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$')


def validate_com_email(value):
    """Validate a practical, normalized email address whose top-level domain is .com."""
    if not isinstance(value, str) or value != value.strip() or len(value) > 254:
        raise ValidationError('Enter a valid .com email address.')

    try:
        local_part, domain = value.rsplit('@', 1)
        ascii_domain = domain.encode('idna').decode('ascii').lower()
    except (ValueError, UnicodeError):
        raise ValidationError('Enter a valid .com email address.')

    normalized = f'{local_part}@{ascii_domain}'
    try:
        validate_email(normalized)
    except ValidationError:
        raise ValidationError('Enter a valid .com email address.')

    labels = ascii_domain.split('.')
    if (
        len(local_part) > 64
        or not LOCAL_PART_RE.fullmatch(local_part)
        or ascii_domain == 'com'
        or not ascii_domain.endswith('.com')
        or any(not DOMAIN_LABEL_RE.fullmatch(label) for label in labels)
    ):
        raise ValidationError('Use a valid email address ending in .com.')
