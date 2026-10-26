interface Vehicle {
    void move();
    void stop();
}

class Car implements Vehicle {
    @Override
    public void move() { System.out.println("汽车在公路上行驶"); }

    @Override
    public void stop() { System.out.println("汽车刹车停止"); }
}

class Ship implements Vehicle {
    @Override
    public void move() { System.out.println("轮船在水面上航行"); }

    @Override
    public void stop() { System.out.println("轮船抛锚停靠"); }
}

public class InterfaceDemo {
    public static void main(String[] args) {
        System.out.println("Java");


        Vehicle car = new Car();
        Vehicle ship = new Ship();

        car.move();  // 输出：汽车在公路上行驶
        ship.move(); // 输出：轮船在水面上航行

        car.stop();  // 输出：汽车刹车停止
        ship.stop(); // 输出：轮船抛锚停靠
    }
}
