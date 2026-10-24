"""Content-addressed immutable originals and Parquet deltas."""
import hashlib
import os
import tempfile
from pathlib import Path
import pyarrow as pa
import pyarrow.parquet as pq

class CorruptVersion(RuntimeError):
    pass

class Store:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _write(self, category, data, extension):
        digest = hashlib.sha256(data).hexdigest()
        relative = f'{category}/{digest[:2]}/{digest}{extension}'
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            fd, tmp = tempfile.mkstemp(dir=target.parent, prefix='.pending-')
            try:
                with os.fdopen(fd, 'wb') as out:
                    out.write(data); out.flush(); os.fsync(out.fileno())
                os.replace(tmp, target)
                os.chmod(target, 0o444)
            finally:
                Path(tmp).unlink(missing_ok=True)
        self.read(relative, digest)
        return relative, digest

    def original(self, raw):
        return self._write('originals', raw, '.csv')

    def delta(self, records):
        # Strings retain exact decimal values; Arrow does not round through binary floats.
        rows = [records[key] for key in sorted(records)]
        table = pa.Table.from_pylist(rows)
        sink = pa.BufferOutputStream()
        pq.write_table(table, sink, compression='zstd')
        return self._write('bars', sink.getvalue().to_pybytes(), '.parquet')

    def read(self, relative, digest):
        path = (self.root / relative).resolve()
        if not path.is_relative_to(self.root.resolve()) or not path.is_file():
            raise CorruptVersion(f'版本文件缺失：{relative}')
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != digest:
            raise CorruptVersion(f'版本文件校验失败：{relative}')
        return data

    def bars(self, files):
        result = {}
        for item in files:
            table = pq.read_table(pa.BufferReader(self.read(item['path'], item['sha256'])))
            for row in table.to_pylist():
                result[f"{row['exchange']}:{row['symbol']}|{row['time']}"] = row
        return result
