pub(crate) enum PriceModInfo {
    Add(f32),
    Multiply(f32),
}

impl PriceModInfo {
    pub(crate) fn apply(&self, price: f32) -> f32 {
        match self {
            PriceModInfo::Add(amount) => price + amount,
            PriceModInfo::Multiply(factor) => price * factor,
        }
    }
}


pub(crate) trait Serialize {
    fn serialize(&self) -> String;
}


pub(crate) trait ModPrice {
    fn get_price_mod(&self) -> &PriceModInfo;
    fn apply_price(&self, price: f32) -> f32 {
        self.get_price_mod().apply(price)
    }
}