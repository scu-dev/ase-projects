mod base;
mod tea_size;
mod tea_kind;
mod milk_tea;
use crate::base::{Serialize};
use crate::milk_tea::Milktea;
use crate::tea_size::{TeaSizeName};
use crate::tea_kind::{TeaKindName};


fn main() {
    let a: [Milktea; 3] = [
        Milktea::new(TeaKindName::Green, TeaSizeName::Large),
        Milktea::new(TeaKindName::Black, TeaSizeName::Medium),
        Milktea::new(TeaKindName::Oolong, TeaSizeName::Small)
    ];
    for m in a {
        println!("Price of {} {} milktea: ${:.2}", m.size.serialize(), m.kind.serialize(), m.price());
    }
}