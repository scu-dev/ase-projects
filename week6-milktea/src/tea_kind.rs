use crate::base::{PriceModInfo, ModPrice, Serialize};

pub(crate) enum TeaKindName {
    Black,
    Green,
}

pub(crate) struct TeaKind {
    name: TeaKindName,
    price_mod: PriceModInfo,
}

impl TeaKind {
    pub(crate) fn new(name: TeaKindName) -> Self {
        match name {
            TeaKindName::Black => TeaKind {
                name,
                price_mod: PriceModInfo::Add(5.0),
            },
            TeaKindName::Green => TeaKind {
                name,
                price_mod: PriceModInfo::Add(6.0),
            },
        }
    }
}

impl Serialize for TeaKind {
    fn serialize(&self) -> String {
        match self.name {
            TeaKindName::Black => "Black".to_string(),
            TeaKindName::Green => "Green".to_string(),
        }
    }
}

impl ModPrice for TeaKind {
    fn get_price_mod(&self) -> &PriceModInfo {
        return &self.price_mod;
    }
}