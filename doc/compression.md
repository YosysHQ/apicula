# Bitstream compression

This algorithm is to apply on a ready to write bitstream, after having computed data configuration checksum and optional padding, before line checksum.

Principle is to replace serie of `0x00` by a dedicated value:
- a serie of `8 * 0x00` is replaced by one value (said `key8Z` in the rest of
  this document);
- a serie of `4 * 0x00` is replaced by one value (said `key4Z` in the rest of
  this document);
- a serie of `2 * 0x00` is replaced by one value (said `key2Z` in the rest of
  this document);

Those values are stored in the header area (line starting with `0x51`), line starting with `0x10` must be updated too (bit 13).

## Optional padding

This algorithm is applied 8 bytes by 8 bytes. So if lines are not multiple of 64bits, a serie of dummy bits (set to `1`) must be added.

## Select values to use

This step consist to search all values not used for data/EBR configuration (it's more or less the creation of an histogram):
```python
lst = [0 for i in range(0, 256)]
for i in range(len(dataCfg)):
	line = dataCfg[i]
	for v in line:
		lst[v] += 1
unusedVal = [i for i,val in enumerate(lst) if val==0]

```
- `key8Z` take the value for index 0 (smallest value)
- `key4Z` take the value for index 1
- `key2Z` take the value for index 2 (highest value)

There may not be enough unused values for some or all keys, in which case the key-specific packing is not performed (in the most severe case, the file is not packed at all if all possible byte values are used).

Line starting with `0x51` must be updated accordingly, and bit `13` for line `0x10` must be set

## Conversion

This step is applied line by line and 8 bytes by 8 bytes.

The principle is more or less to find/replace sequentially series of `0x00`:

For example:
- `[0x00 0x00 0x00 0x00 0x00 0x00 0x00 0x00]`
  - `[key8Z]`
- `[0x00 0x00 0x00 0x00 0x00 0x00 0x00 0xFF]`
  - `[key4Z 0x00 0x00 0x00 0xFF]`
    - `[key4Z key2Z 0x00 0xFF]`
