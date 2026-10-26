#include <iostream>

// 移动策略接口（抽象基类）
class MoveStrategy {
public:
    virtual void move() = 0; // 纯虚函数，定义移动接口
    virtual ~MoveStrategy() = default; // 虚析构函数，确保派生类正确析构
};

// 公路行驶策略
class RoadMoveStrategy : public MoveStrategy {
public:
    void move() override {
        std::cout << "在公路上行驶" << std::endl;
    }
};

// 水面航行策略
class WaterMoveStrategy : public MoveStrategy {
public:
    void move() override {
        std::cout << "在水面上航行" << std::endl;
    }
};

// 交通工具抽象类
class Vehicle {
protected:
    MoveStrategy* moveStrategy; // 持有移动策略指针

public:
    // 构造函数：初始化移动策略
    Vehicle(MoveStrategy* strategy) : moveStrategy(strategy) {}

    // 析构函数：释放策略对象
    virtual ~Vehicle() {
        delete moveStrategy;
    }

    // 执行移动（委托给策略）
    void move() {
        moveStrategy->move();
    }

    // 切换移动策略
    void setMoveStrategy(MoveStrategy* newStrategy) {
        delete moveStrategy; // 释放旧策略
        moveStrategy = newStrategy; // 更换新策略
    }

    // 纯虚函数：获取交通工具名称
    virtual const char* getName() const = 0;
};

// 汽车类
class Car : public Vehicle {
public:
    Car() : Vehicle(new RoadMoveStrategy()) {}

    const char* getName() const override {
        return "汽车";
    }
};

// 轮船类
class Ship : public Vehicle {
public:
    Ship() : Vehicle(new WaterMoveStrategy()) {}

    const char* getName() const override {
        return "轮船";
    }
};

// 坦克类（水陆两栖）
class Tank : public Vehicle {
public:
    Tank() : Vehicle(new RoadMoveStrategy()) {} // 默认陆地模式

    // 切换到陆地模式
    void moveOnRoad() {
        setMoveStrategy(new RoadMoveStrategy());
        std::cout << "坦克已切换到陆地模式" << std::endl;
    }

    // 切换到水上模式
    void moveOnWater() {
        setMoveStrategy(new WaterMoveStrategy());
        std::cout << "坦克已切换到水上模式" << std::endl;
    }

    const char* getName() const override {
        return "坦克";
    }
};

// 主函数测试
int main() {
    // 确保中文正常显示（Windows系统）
    #ifdef _WIN32
    system("chcp 65001 > null"); // 切换到UTF-8编码
    #endif

    Vehicle* car = new Car();
    Vehicle* ship = new Ship();
    Tank* tank = new Tank();

    // 汽车移动
    std::cout << car->getName() << "：";
    car->move();

    // 轮船移动
    std::cout << ship->getName() << "：";
    ship->move();

    // 坦克初始移动（陆地模式）
    std::cout << tank->getName() << "：";
    tank->move();

    // 坦克切换到水上模式
    tank->moveOnWater();
    std::cout << tank->getName() << "：";
    tank->move();

    // 坦克切换回陆地模式
    tank->moveOnRoad();
    std::cout << tank->getName() << "：";
    tank->move();

    // 释放资源
    delete car;
    delete ship;
    delete tank;

    return 0;
}
