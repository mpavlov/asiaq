# convert wg_rpmbuild's template values to regular rpm template values
# _topdir defines the root of the rpm staging area. the value is passed automatically by wg_rpmbuild
%define _topdir $_topdir
%define checkoutroot $checkoutroot
%define version $version
%define build_number $build_number

Summary: Asiaq Automation for AWS
Name: asiaq
Version: %{version}
Release: %{build_number}
License: EULA
Group: Applications/AWS
BuildArch: x86_64
BuildRoot: %{_tmppath}/%{name}-%{version}-%{release}-buildroot

BuildRequires: wgen-python27
BuildRequires: wgen-python27-setuptools
BuildRequires: wgen-python27-virtualenv

Requires: wgen-python27

%description


%prep
mkdir -p %{buildroot}/opt/wgen/asiaq
# Annoyingly, the RPM workspace is right on top
# of the project checkout. We want to copy everything
# that isn't one of the RPM directories into the BUILD dir.
shopt -s extglob
cp -r %{checkoutroot}/asiaq/!(BUILD|BUILDROOT|RPMS|SOURCES|SPEC|SPRMS) .

%build
# remove the virtual env prior to building to ensure proper updates
rm -rf build_venv
/opt/wgen-3p/python27/bin/virtualenv --no-site-packages build_venv
source build_venv/bin/activate
# inject_rpm needs the dependencies installed first, so do a setup:install_deps
rake setup:install_deps
rake version:inject_git
env RPM_BUILD=%{build_number} rake version:inject_rpm
env CFLAGS="$RPM_OPT_FLAGS" rake setup:install
deactivate
/opt/wgen-3p/python27/bin/virtualenv --relocatable build_venv

%install
cp -r build_venv/* %{buildroot}/opt/wgen/asiaq
find %{buildroot}/opt/wgen/asiaq -type f -print0 -perm +111 -name '.py' | xargs -0 sed -i'' -e '1s|^#!.*python.*|#!/opt/wgen/asiaq/bin/python|'

#Generate a file list for packaging
find %{buildroot}/opt/wgen/asiaq/* -type d | sed -e 's#^%{buildroot}#%dir "#' -e 's#$#"#' > INSTALLED_FILES
find %{buildroot}/opt/wgen/asiaq/* -not -type d | sed -e 's#^%{buildroot}#"#' -e 's#$#"#' >> INSTALLED_FILES

%files -f INSTALLED_FILES
%defattr(-,root,root)

%clean
rm -Rf %{buildroot}
