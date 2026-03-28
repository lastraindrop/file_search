import PyInstaller.__main__
import os
import shutil

def build():
    # 确保在当前目录下运行
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)

    print("开始打包桌面版 (EXE)...")
    
    # PyInstaller 参数说明:
    # --onefile: 打包成单个文件
    # --noconsole: 运行时不显示黑色命令行窗口
    # --clean: 清除上次打包的临时文件
    # --name: 指定输出的文件名
    # --add-data: 如果有额外的静态资源可以在这里添加
    
    params = [
        'file_search.py',
        '--onefile',
        '--noconsole',
        '--clean',
        '--name=FileCortex',
        '--add-data=static;static',
        '--add-data=templates;templates',
        '--collect-all=file_cortex_core',
        # If you have an icon, uncomment below
        # '--icon=app.ico', 
    ]

    PyInstaller.__main__.run(params)

    # 清理临时目录
    print("\n打包完成！")
    print("可执行文件位于: dist/FileCortex.exe")
    
    if os.path.exists("build"):
        shutil.rmtree("build")
    spec_file = "FileCortex.spec"
    if os.path.exists(spec_file):
        os.remove(spec_file)

if __name__ == "__main__":
    build()
