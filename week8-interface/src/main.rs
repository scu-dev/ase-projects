trait Vehicle {
    fn toggle_mode(&mut self);
    fn _move(&self);
    fn stop(&self);
}

#[derive(Eq, PartialEq)]
enum MoveMode {
    Land,
    Water,
    Air
}
impl MoveMode {
    fn get_mode(&self) -> &str {
        match self {
            MoveMode::Land => "land",
            MoveMode::Water => "water",
            MoveMode::Air => "air",
        }
    }
    fn toggle(&mut self, new_mode: MoveMode) {
        *self = new_mode;
    }
}

struct Car {
    mode: MoveMode,
}

impl Car {
    fn new() -> Self {
        Car { mode: MoveMode::Land }
    }
}

impl Vehicle for Car {
    fn _move(&self) {
        println!("The car is moving on/in {}.", self.mode.get_mode());
    }
    fn stop(&self) {
        println!("The car has stopped.");
    }
    fn toggle_mode(&mut self) {
        println!("Cars cannot toggle modes. They are always in {} mode.", self.mode.get_mode());
    }
}

struct Ship {
    mode: MoveMode,
}

impl Ship {
    fn new() -> Self {
        Ship { mode: MoveMode::Water }
    }
}

impl Vehicle for Ship {
    fn _move(&self) {
        println!("The ship is moving on/in {}.", self.mode.get_mode());
    }
    fn stop(&self) {
        println!("The ship has anchored.");
    }
    fn toggle_mode(&mut self) {
        println!("Ships cannot toggle modes. They are always in {} mode.", self.mode.get_mode());
    }
}

struct Tank {
    mode: MoveMode,
}

impl Tank {
    fn new() -> Self {
        Tank { mode: MoveMode::Land }
    }
}

impl Vehicle for Tank {
    fn _move(&self) {
        println!("The tank is moving on/in {}.", self.mode.get_mode());
    }
    fn stop(&self) {
        println!("The tank has stopped.");
    }
    fn toggle_mode(&mut self) {
        if self.mode == MoveMode::Land {
            self.mode.toggle(MoveMode::Water);
            println!("The tank has toggled to {} mode.", self.mode.get_mode());
        }
        else {
            self.mode.toggle(MoveMode::Land);
            println!("The tank has toggled to {} mode.", self.mode.get_mode());
        }
    }
}

fn main() {
    let car = Car::new();
    let ship = Ship::new();
    let mut tank = Tank::new();
    let a: &dyn Vehicle = &car;
    let b: &dyn Vehicle = &ship;
    let c: &mut dyn Vehicle = &mut tank;

    a._move();
    b._move();
    c._move();

    c.toggle_mode();
    c._move();
    c.toggle_mode();
    c._move();

    a.stop();
    b.stop();
    c.stop();
}