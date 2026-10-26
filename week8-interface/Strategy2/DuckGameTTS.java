package Strategy2;

import java.io.IOException;

/**
 * 小鸭行为与叫声 + TTS 实时播放
 */

public class DuckGameTTS {
    /* ================= 行为策略 ================= */
    interface BehaviorStrategy { void perform(); }

    static class JumpBehavior implements BehaviorStrategy {
        public void perform() {
            System.out.println("===行为：蹦蹦跳跳");
        }
    }

    static class SpinBehavior implements BehaviorStrategy {
        public void perform() {
            System.out.println("===行为：转圈圈");
        }
    }

    static class FlyBehavior implements BehaviorStrategy {
        public void perform() {
            System.out.println("===行为：飞起来了");
        }
    }

    /* ================= 叫声策略 ================= */
    interface SoundStrategy { void makeSound(); }

    /* 封装 TTS */
    static class TTSUtil {
        public static void speak(String text) {
            try {
                String cmd;
                String os = System.getProperty("os.name").toLowerCase();
                if (os.contains("win")) {
                    // PowerShell 调用 SAPI
                    cmd = "powershell -ExecutionPolicy Bypass -Command \"Add-Type –AssemblyName System.Speech; " +
                            "(New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak('" + text + "');\"";
                } else if (os.contains("mac")) {
                    cmd = "say " + text;
                } else {               // Linux
                    cmd = "espeak \"" + text + "\"";
                }
                new ProcessBuilder(cmd.split(" ")).inheritIO().start().waitFor();
            } catch (IOException | InterruptedException e) {
                System.err.println("TTS 失败: " + e.getMessage());
            }
        }
    }

    /* 三种叫声策略 */
    static class QuackSound implements SoundStrategy {
        public void makeSound() {
            String txt = "嘎嘎嘎好开心";
            System.out.println("===叫声：" + txt);
            TTSUtil.speak(txt);
        }
    }

    static class MeowSound implements SoundStrategy {
        public void makeSound() {
            String txt = "喵喵喵好漂亮";
            System.out.println("===叫声：" + txt);
            TTSUtil.speak(txt);
        }
    }

    static class BarkSound implements SoundStrategy {
        public void makeSound() {
            String txt = "汪汪汪太酷了";
            System.out.println("===叫声：" + txt);
            TTSUtil.speak(txt);
        }
    }

    /* ================= 小鸭 ================= */
    static class Duck {
        private BehaviorStrategy behavior;
        private SoundStrategy sound;

        public void setBehavior(BehaviorStrategy b) {
            this.behavior = b;
        }

        public void setSound(SoundStrategy s) {
            this.sound = s;
        }

        public void act() {
            behavior.perform();
            sound.makeSound();
        }
    }

    public static void main(String[] args) throws Exception {
        Duck duck = new Duck();

        System.out.println("1. 小鸭抢到红包");
        duck.setBehavior(new JumpBehavior());
        duck.setSound(new QuackSound());
        duck.act();

        System.out.println("2. 小鸭拿着红包买到新衣服");
        duck.setBehavior(new SpinBehavior());
        duck.setSound(new MeowSound());
        duck.act();

        System.out.println("3. 小鸭穿上新衣服");
        duck.setBehavior(new FlyBehavior());
        duck.setSound(new BarkSound());
        duck.act();
    }
}