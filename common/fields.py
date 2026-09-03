"""加密字段: 用 SECRET_KEY 派生的 Fernet 密钥透明加密字符串。"""
from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import models


def _fernet() -> Fernet:
    digest = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


class EncryptedCharField(models.CharField):
    """透明加解密 CharField: 落库为 enc: 前缀密文, 读出自动解密。

    兼容历史明文数据(解密失败则原样返回, 下次保存自动升级为密文)。
    """

    PREFIX = "enc:"

    def _decrypt(self, value):
        if isinstance(value, str) and value.startswith(self.PREFIX):
            try:
                return _fernet().decrypt(value[len(self.PREFIX):].encode("utf-8")).decode("utf-8")
            except (InvalidToken, ValueError):
                return value
        return value

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if not value:
            return value
        if isinstance(value, str) and value.startswith(self.PREFIX):
            return value
        return self.PREFIX + _fernet().encrypt(str(value).encode("utf-8")).decode("utf-8")

    def from_db_value(self, value, expression, connection):
        return self._decrypt(value)

    def to_python(self, value):
        return self._decrypt(super().to_python(value))
