/**
g++ InterfaceDemo.cpp  -finput-charset=UTF-8 -fexec-charset=GBK -o InterfaceDemo
**/
#include <iostream>

// 定义一个"接口"（包含纯虚函数的抽象类）
class Vehicle {
public:
    // 纯虚函数：只有声明，没有实现
    virtual void move() = 0;
    virtual void stop() = 0;
    
    // 接口类通常需要虚析构函数，确保派生类析构正确调用
    virtual ~Vehicle() = default;
};

// 实现接口：Car类继承Vehicle并实现所有纯虚函数
class Car : public Vehicle {
public:
    void move() override {
        std::cout << "汽车在公路上行驶" << std::endl;
    }
    
    void stop() override {
        std::cout << "汽车刹车停止" << std::endl;
    }
};

// 实现接口：Ship类继承Vehicle并实现所有纯虚函数
class Ship : public Vehicle {
public:
    void move() override {
        std::cout << "轮船在水面上航行" << std::endl;
    }
    
    void stop() override {
        //std::cout << "轮船抛锚停靠" << std::endl;
        printf("轮船抛锚停靠\r\n");
    }
};

class Airplane : public Vehicle {
public:
    void move() override {
        std::cout << "飞机在天空中飞行" << std::endl;
    }
    void stop() override {
        std::cout << "飞机降落停止" << std::endl;
    }
};

int main() {
    std::cout << "C++\r\n";

    // 不能实例化接口，但可以声明接口指针/引用
    Vehicle* car = new Car();
    Vehicle* ship = new Ship();
    Vehicle* airplane = new Airplane();
    
    car->move();  // 输出：汽车在公路上行驶
    ship->move(); // 输出：轮船在水面上航行
    airplane->move(); // 输出：飞机在天空中飞行
    
    car->stop();  // 输出：汽车刹车停止
    ship->stop(); // 输出：轮船抛锚停靠
    airplane->stop(); // 输出：飞机降落停止
    
    delete car;
    delete ship;
    delete airplane;
    return 0;
}