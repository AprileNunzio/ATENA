use std::io::{self, Read};

const MAGIC_MICROS: u32 = 0xa1b2_c3d4;
const MAGIC_NANOS: u32 = 0xa1b2_3c4d;
const LINKTYPE_ETHERNET: u32 = 1;
const MAX_RECORD: usize = 262_144;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Record {
    pub at_ms: u64,
    pub data: Vec<u8>,
}

#[derive(Debug)]
pub struct Reader<R: Read> {
    input: R,
    swapped: bool,
    nanos: bool,
}

fn invalid(message: &str) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, message.to_owned())
}

fn word(raw: [u8; 4], swapped: bool) -> u32 {
    if swapped {
        u32::from_be_bytes(raw)
    } else {
        u32::from_le_bytes(raw)
    }
}

impl<R: Read> Reader<R> {
    pub fn open(mut input: R) -> io::Result<Self> {
        let mut header = [0_u8; 24];
        input.read_exact(&mut header)?;
        let magic: [u8; 4] = header
            .get(0..4)
            .and_then(|s| s.try_into().ok())
            .ok_or_else(|| invalid("header"))?;
        let (swapped, nanos) = match (u32::from_le_bytes(magic), u32::from_be_bytes(magic)) {
            (MAGIC_MICROS, _) => (false, false),
            (MAGIC_NANOS, _) => (false, true),
            (_, MAGIC_MICROS) => (true, false),
            (_, MAGIC_NANOS) => (true, true),
            _ => return Err(invalid("non è un file pcap")),
        };
        let link: [u8; 4] = header
            .get(20..24)
            .and_then(|s| s.try_into().ok())
            .ok_or_else(|| invalid("header"))?;
        if word(link, swapped) != LINKTYPE_ETHERNET {
            return Err(invalid("solo catture Ethernet"));
        }
        Ok(Self {
            input,
            swapped,
            nanos,
        })
    }

    pub fn next_record(&mut self) -> io::Result<Option<Record>> {
        let mut header = [0_u8; 16];
        match self.input.read_exact(&mut header) {
            Ok(()) => {}
            Err(e) if e.kind() == io::ErrorKind::UnexpectedEof => return Ok(None),
            Err(e) => return Err(e),
        }
        let field = |at: usize| -> io::Result<u32> {
            let raw: [u8; 4] = header
                .get(at..at.saturating_add(4))
                .and_then(|s| s.try_into().ok())
                .ok_or_else(|| invalid("record"))?;
            Ok(word(raw, self.swapped))
        };
        let seconds = u64::from(field(0)?);
        let fraction = u64::from(field(4)?);
        let captured = usize::try_from(field(8)?).map_err(|_| invalid("record"))?;
        if captured > MAX_RECORD {
            return Err(invalid("record troppo grande"));
        }
        let mut data = vec![0_u8; captured];
        self.input.read_exact(&mut data)?;
        let millis = if self.nanos {
            fraction / 1_000_000
        } else {
            fraction / 1_000
        };
        Ok(Some(Record {
            at_ms: seconds.saturating_mul(1_000).saturating_add(millis),
            data,
        }))
    }
}
