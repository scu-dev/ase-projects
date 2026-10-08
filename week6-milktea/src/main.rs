mod base;
mod tea_size;
mod tea_kind;
mod milk_tea;
use crate::base::{Serialize};
use crate::milk_tea::Milktea;
use crate::tea_size::TeaSizeName;
use crate::tea_kind::TeaKindName;


fn main() {
    let a = Milktea::new(TeaKindName::Green, TeaSizeName::Large);
    println!("Price of {} {} Milktea: ${:.2}", a.size.serialize(), a.kind.serialize(), a.price());
}