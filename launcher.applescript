on run
	set selfPath to POSIX path of (path to me)
	do shell script "self_path=" & quoted form of selfPath & "; project_dir=$(dirname \"$self_path\"); python_bin=\"$project_dir/.venv/bin/python\"; if [ ! -x \"$python_bin\" ]; then python_bin=$(command -v python3); fi; cd \"$project_dir\" && \"$python_bin\" \"$project_dir/定格截图.py\" >/tmp/dingge-screenshot.log 2>&1 &"
end run
