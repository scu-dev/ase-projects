use crate::base::ModPrice;
use crate::tea_kind::{TeaKind, TeaKindName};
use crate::tea_size::{TeaSize, TeaSizeName};

pub(crate) struct Milktea {
    pub kind: TeaKind,
    pub size: TeaSize,
}

impl Milktea {
    pub(crate) fn new(kind: TeaKindName, size: TeaSizeName) -> Milktea {
        Milktea {
            kind: TeaKind::new(kind),
            size: TeaSize::new(size)
        }
    }

    pub(crate) fn price(&self) -> f32 {
        let mut price = 0.0;
        price = self.kind.apply_price(price);
        price = self.size.apply_price(price);
        price
    }
}