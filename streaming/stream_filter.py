"""LLM stream token filter and chunking logic."""

import re

# Advanced Regex for sentence boundaries (negative lookbehinds for abbreviations, decimals)
_SENTENCE_BOUNDARY = re.compile(
    r'(?<!\b[A-Z][a-z]\.)(?<!\b[A-Z]\.)(?<!\w\.\w\.)(?<=\.|\?|!)\s+(?=[A-Z0-9])'
)
_PHRASE_BOUNDARY = re.compile(r'(?<=,|;|:)\s+')
_STRIP_MARKDOWN = re.compile(r'[*_~`]')


class StreamFilterAndSplitter:
    def __init__(self, first_chunk_min=40, next_chunk_min=150):
        self.buffer = ""
        self.think_buffer = ""
        self.in_think = False
        self.is_first_chunk = True
        self.first_chunk_min = first_chunk_min
        self.next_chunk_min = next_chunk_min

    def push(self, token: str) -> list[str]:
        chunks = []
        for char in token:
            if not self.in_think:
                self.buffer += char
                if self.buffer.endswith("<think>"):
                    self.in_think = True
                    self.buffer = self.buffer[:-7]
            else:
                self.think_buffer += char
                if self.think_buffer.endswith("</think>"):
                    self.in_think = False
                    self.think_buffer = ""
        
        if self.in_think:
            return chunks

        # Prevent splitting if a tag is being formed
        if "<" in self.buffer[-7:]:
            return chunks
            
        while True:
            target_len = self.first_chunk_min if self.is_first_chunk else self.next_chunk_min
            if len(self.buffer) < target_len:
                break
                
            split_idx = -1
            
            if self.is_first_chunk:
                # Can split on phrase boundary or sentence boundary
                matches = list(_PHRASE_BOUNDARY.finditer(self.buffer)) + list(_SENTENCE_BOUNDARY.finditer(self.buffer))
                
                best_match = None
                for m in matches:
                    if m.start() >= self.first_chunk_min:
                        if not best_match or m.start() < best_match.start():
                            best_match = m
                if best_match:
                    split_idx = best_match.end()
            else:
                # Must be a sentence boundary
                matches = list(_SENTENCE_BOUNDARY.finditer(self.buffer))
                for m in matches:
                    if m.start() >= self.next_chunk_min:
                        split_idx = m.end()
                        break
            
            if split_idx == -1 and len(self.buffer) > 250:
                 # Fallback: force a split on space if it gets too large
                 space_idx = self.buffer.rfind(' ', 0, 250)
                 if space_idx != -1:
                     split_idx = space_idx + 1
            
            if split_idx != -1:
                chunk = self.buffer[:split_idx].strip()
                self.buffer = self.buffer[split_idx:]
                chunk = _STRIP_MARKDOWN.sub('', chunk)
                if chunk:
                    chunks.append(chunk)
                    self.is_first_chunk = False
            else:
                break
                
        return chunks
        
    def flush(self) -> str:
        if self.in_think:
            return ""
        chunk = self.buffer.strip()
        chunk = _STRIP_MARKDOWN.sub('', chunk)
        self.buffer = ""
        return chunk
