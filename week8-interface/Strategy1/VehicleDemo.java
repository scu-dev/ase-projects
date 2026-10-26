// 移动策略接口（定义移动行为规范）
interface MoveStrategy {
    void move();
}

// 公路行驶策略
class RoadMoveStrategy implements MoveStrategy {
    @Override
    public void move() {
        System.out.println("在公路上行驶");
    }
}

// 水面航行策略
class WaterMoveStrategy implements MoveStrategy {
    @Override
    public void move() {
        System.out.println("在水面上航行");
    }
}

// 交通工具抽象类（持有移动策略）
abstract class Vehicle {
    protected MoveStrategy moveStrategy;
    
    public Vehicle(MoveStrategy moveStrategy) {
        this.moveStrategy = moveStrategy;
    }
    
    public void move() {
        moveStrategy.move();
    }
    
    // 提供策略切换方法（坦克需要此功能）
    public void setMoveStrategy(MoveStrategy moveStrategy) {
        this.moveStrategy = moveStrategy;
    }
}

// 汽车（仅能公路行驶）
class Car extends Vehicle {
    public Car() {
        super(new RoadMoveStrategy());
    }
    
    @Override
    public String toString() {
        return "汽车";
    }
}

// 轮船（仅能水面航行）
class Ship extends Vehicle {
    public Ship() {
        super(new WaterMoveStrategy());
    }
    
    @Override
    public String toString() {
        return "轮船";
    }
}

// 坦克（水陆两栖，可切换移动方式）
class Tank extends Vehicle {
    public Tank() {
        // 默认使用公路行驶策略
        super(new RoadMoveStrategy());
    }
    
    // 切换到公路行驶
    public void moveOnRoad() {
        setMoveStrategy(new RoadMoveStrategy());
        System.out.println("坦克已切换到陆地模式");
    }
    
    // 切换到水面航行
    public void moveOnWater() {
        setMoveStrategy(new WaterMoveStrategy());
        System.out.println("坦克已切换到水上模式");
    }
    
    @Override
    public String toString() {
        return "坦克";
    }
}

// 测试类
public class VehicleDemo {
    public static void main(String[] args) {
        Vehicle car = new Car();
        Vehicle ship = new Ship();
        Tank tank = new Tank();
        
        // 汽车移动
        System.out.print(car + "：");
        car.move();
        
        // 轮船移动
        System.out.print(ship + "：");
        ship.move();
        
        // 坦克初始移动（陆地模式）
        System.out.print(tank + "：");
        tank.move();
        
        // 坦克切换到水上模式
        tank.moveOnWater();
        System.out.print(tank + "：");
        tank.move();
        
        // 坦克切换回陆地模式
        tank.moveOnRoad();
        System.out.print(tank + "：");
        tank.move();
    }
}
