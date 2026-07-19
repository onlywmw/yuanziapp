# tokenizer.py — bert 中文 WordPiece 分词器（纯标准库，不依赖 transformers）
"""
供 OnnxProvider 使用：加载 bert 中文 vocab.txt（21128 词，行号即 token id），
先做基础分词（小写 → 中文逐字 → 空白/标点切分），再做 WordPiece 贪心最长
匹配（子词带 "##" 前缀），输出 bge 模型所需的 input_ids / attention_mask /
token_type_ids（batch 维为 1，不加 padding，按实际长度送入推理）。
"""
import unicodedata

DEFAULT_MAX_LEN = 64  # 意图短句足够，限制序列长度避免拖慢 CPU 推理
MAX_CHARS_PER_WORD = 100  # 超过此长度的词直接判 [UNK]（bert 官方做法）


def _is_chinese_char(ch):
    """是否 CJK 统一表意文字（含扩展区与兼容表意文字），逐字成 token。"""
    cp = ord(ch)
    return (
        0x4E00 <= cp <= 0x9FFF
        or 0x3400 <= cp <= 0x4DBF
        or 0x20000 <= cp <= 0x2A6DF
        or 0x2A700 <= cp <= 0x2B73F
        or 0x2B740 <= cp <= 0x2B81F
        or 0x2B820 <= cp <= 0x2CEAF
        or 0xF900 <= cp <= 0xFAFF
        or 0x2F800 <= cp <= 0x2FA1F
    )


def _is_whitespace(ch):
    return ch in " \t\n\r" or unicodedata.category(ch) == "Zs"


def _is_control(ch):
    if ch in "\t\n\r":
        return False
    return unicodedata.category(ch) in ("Cc", "Cf")


def _is_punctuation(ch):
    cp = ord(ch)
    # ASCII 标点按区间判断，其余按 Unicode 类别 P*
    if 33 <= cp <= 47 or 58 <= cp <= 64 or 91 <= cp <= 96 or 123 <= cp <= 126:
        return True
    return unicodedata.category(ch).startswith("P")


class WordPieceTokenizer:
    """bert 中文分词：基础分词 + WordPiece 贪心最长匹配。"""

    def __init__(self, vocab_path, max_len=DEFAULT_MAX_LEN):
        self.vocab = {}  # token → id（vocab.txt 行号）
        with open(vocab_path, encoding="utf-8") as f:
            for idx, line in enumerate(f):
                token = line.rstrip("\r\n")
                if token:
                    self.vocab[token] = idx
        if "[UNK]" not in self.vocab:
            raise ValueError("vocab.txt 缺少必需的 [UNK] 标记")
        self.unk_id = self.vocab["[UNK]"]
        self.cls_id = self.vocab.get("[CLS]", 101)
        self.sep_id = self.vocab.get("[SEP]", 102)
        self.max_len = max_len

    def tokenize(self, text):
        """文本 → token 序列（不含 [CLS]/[SEP]）。"""
        tokens = []
        for word in self._basic_tokenize(text.lower()):
            tokens.extend(self._wordpiece(word))
        return tokens

    def encode(self, text):
        """文本 → 模型输入（含 [CLS]/[SEP]，截断到 max_len，batch 维为 1）。"""
        tokens = self.tokenize(text)[: self.max_len - 2]
        ids = [self.cls_id]
        ids.extend(self.vocab.get(t, self.unk_id) for t in tokens)
        ids.append(self.sep_id)
        mask = [1] * len(ids)
        return {
            "input_ids": [ids],
            "attention_mask": [mask],
            "token_type_ids": [[0] * len(ids)],
        }

    # ---------- 基础分词 ----------

    @staticmethod
    def _basic_tokenize(text):
        """清洗控制字符 → 中文逐字切开 → 按空白与标点切词。"""
        words = []
        buf = []

        def flush():
            if buf:
                words.append("".join(buf))
                buf.clear()

        for ch in text:
            if _is_control(ch):
                continue
            if _is_chinese_char(ch):
                flush()
                words.append(ch)
            elif _is_whitespace(ch):
                flush()
            elif _is_punctuation(ch):
                flush()
                words.append(ch)
            else:
                buf.append(ch)
        flush()
        return words

    # ---------- WordPiece ----------

    def _wordpiece(self, word):
        """单词 → 子词序列；无法覆盖时整个词判 [UNK]。"""
        if len(word) > MAX_CHARS_PER_WORD:
            return ["[UNK]"]
        sub_tokens = []
        start = 0
        while start < len(word):
            end = len(word)
            hit = None
            while start < end:
                piece = word[start:end]
                if start > 0:
                    piece = "##" + piece
                if piece in self.vocab:
                    hit = piece
                    break
                end -= 1
            if hit is None:
                return ["[UNK]"]
            sub_tokens.append(hit)
            start = end
        return sub_tokens
