use crate::base::{PriceModInfo, ModPrice, Serialize};

pub(crate) enum TeaSizeName {
    Small,
    Medium,
    Large,
}

pub(crate) struct TeaSize {
    name: TeaSizeName,
    price_mod: PriceModInfo,
}

impl TeaSize {
    pub(crate) fn new(name: TeaSizeName) -> Self {
        match name {
            TeaSizeName::Small => TeaSize {
                name,
                price_mod: PriceModInfo::Multiply(1.0),
            },
            TeaSizeName::Medium => TeaSize {
                name,
                price_mod: PriceModInfo::Multiply(1.5),
            },
            TeaSizeName::Large => TeaSize {
                name,
                price_mod: PriceModInfo::Multiply(2.0),
            },
        }
    }
}

impl Serialize for TeaSize {
    fn serialize(&self) -> String {
        match self.name {
            TeaSizeName::Small => "Small".to_string(),
            TeaSizeName::Medium => "Medium".to_string(),
            TeaSizeName::Large => "Large".to_string(),
        }
    }
}

impl ModPrice for TeaSize {
    fn get_price_mod(&self) -> &PriceModInfo {
        return &self.price_mod;
    }
}