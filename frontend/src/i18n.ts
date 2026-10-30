export type Language = 'en' | 'ar';
export type Theme = 'light' | 'dark';

export interface Translations {
  // Auth
  signin_heading: string;
  signin_sub: string;
  signup_heading: string;
  signup_sub: string;
  name_label: string;
  email_label: string;
  password_label: string;
  btn_signin: string;
  btn_signup: string;
  btn_google: string;
  switch_to_signup: string;
  switch_to_signin: string;
  signing_in: string;
  auth_error_generic: string;
  sign_out: string;
  welcome_back: string;
  signed_in_as: string;

  brand_name: string;
  brand_sub: string;
  workspace: string;
  nav_overview: string;
  nav_profiles: string;
  nav_history: string;
  nav_diary: string;
  system_status: string;
  api_unavailable: string;
  local_dashboard: string;
  version: string;

  topbar_eyebrow: string;
  topbar_h1: string;
  topbar_em: string;
  download_app: string;
  live_data: string;
  refresh_rate: string;
  refresh_label: string;
  theme_toggle_to_dark: string;
  theme_toggle_to_light: string;
  lang_toggle: string;

  error_title: string;
  error_desc: string;
  retry: string;

  currently_monitoring: string;
  species_unconfirmed: string;
  growth_stage_unset: string;
  auto_mode_exec: string;
  auto_mode_locked: string;
  manual_control: string;
  last_sensor_update: string;
  no_telemetry_received: string;
  water_now: string;
  switch_to_manual: string;
  switch_to_auto: string;
  run_check: string;
  watering_duration: string;
  safety_limit: string;
  root_moisture: string;
  vpd_index: string;

  sensor_network: string;
  env_conditions: string;
  receiving_telemetry: string;
  waiting_telemetry: string;

  metric_surface: string;
  metric_mid: string;
  metric_root: string;
  metric_temp: string;
  metric_humidity: string;
  metric_leaf_wetness: string;
  fresh_reading: string;
  no_fresh_reading: string;
  primary_signal: string;
  missing_stale: string;
  dht22_label: string;
  optional_sensor: string;
  not_implemented: string;

  last_readings: string;
  soil_trends: string;
  sensor_history_tag: string;
  surface_legend: string;
  mid_legend: string;
  root_legend: string;
  waiting_first_readings: string;
  mqtt_hint: string;
  timestamp_note: string;
  records_loaded: string;

  plant_climate: string;
  stress_indicators: string;
  vpd_band: string;
  vpd_desc: string;
  forecast_available: string;
  rain_probability: string;
  weather_not_configured: string;
  next_forecast_rain: string;
  weather_env_hint: string;

  gemini_vision: string;
  latest_photo: string;
  no_photo_yet: string;
  cam_interval: string;
  captured_prefix: string;
  waiting_cam: string;
  status_analyzed: string;
  status_stored: string;
  status_awaiting: string;
  analyze_photo_btn: string;
  observed_label: string;
  possible_stress_label: string;
  vision_disclaimer: string;

  decision_engine: string;
  recent_decisions: string;
  no_decisions: string;

  plant_knowledge: string;
  ask_plant: string;
  data_grounded: string;
  assistant_intro: string;
  chat_placeholder: string;
  send_btn: string;
  assistant_name: string;
  prompt_root: string;
  prompt_analyze: string;
  prompt_summary: string;

  knowledge_base: string;
  plant_profile: string;
  add_plant: string;
  ideal_range: string;
  source_label: string;
  source_manual: string;
  source_ai: string;
  source_unconfirmed: string;
  species_override_label: string;
  species_placeholder: string;
  save_species: string;
  species_db_hint: string;

  form_plant_id: string;
  form_name: string;
  form_species: string;
  form_stage: string;
  form_min_moist: string;
  form_max_moist: string;
  form_save: string;

  daily_notes: string;
  plant_diary: string;
  generate_entry: string;
  diary_generated_from: string;
  no_diary_yet: string;

  footer_prototype: string;
  footer_freshness_warning: string;

  download_eyebrow: string;
  download_title: string;
  download_desc: string;
  android_app: string;
  android_sub: string;
  ios_app: string;
  ios_sub: string;
  install: string;
  build_required: string;
  signing_required: string;
  install_this_device: string;
  native_setup: string;
  install_this_desc: string;
  native_setup_desc: string;
  iphone_add_to_home: string;
  native_docs_link: string;
  close: string;

  syncing_data: string;
  mode_changed: string;
  water_queued: string;
  water_not_sent: string;
  device_online: string;
  device_stale: string;
  device_offline: string;
  read_only_notice: string;
  last_command: string;
  use_as_species: string;
  species_candidate_note: string;
  cmd_published_waiting: string;
  decision_prefix: string;
  species_saved_prefix: string;
  species_cleared: string;
  photo_analyzed_prefix: string;
  diary_generated: string;
  plant_profile_created: string;
}

export const translations: Record<Language, Translations> = {
  en: {
    // Auth
    signin_heading: 'Welcome back',
    signin_sub: 'Sign in to access your plant dashboard',
    signup_heading: 'Create your account',
    signup_sub: 'Start monitoring your plants with AI-powered insights',
    name_label: 'Full name',
    email_label: 'Email address',
    password_label: 'Password',
    btn_signin: 'Sign in',
    btn_signup: 'Create account',
    btn_google: 'Continue with Google',
    switch_to_signup: "Don't have an account? Sign up",
    switch_to_signin: 'Already have an account? Sign in',
    signing_in: 'Signing in…',
    auth_error_generic: 'Something went wrong. Please try again.',
    sign_out: 'Sign out',
    welcome_back: 'Welcome back',
    signed_in_as: 'Signed in as',

    brand_name: 'Greetopia',
    brand_sub: 'PLANT INTELLIGENCE',
    workspace: 'WORKSPACE',
    nav_overview: 'Overview',
    nav_profiles: 'Plant profiles',
    nav_history: 'Sensor history',
    nav_diary: 'Plant diary',
    system_status: 'System status',
    api_unavailable: 'API unavailable',
    local_dashboard: 'Local dashboard',
    version: 'GREETOPIA · v0.1',

    topbar_eyebrow: 'YOUR GROWING SPACE / OVERVIEW',
    topbar_h1: 'Plant care,',
    topbar_em: 'in sync.',
    download_app: 'Download app',
    live_data: 'LIVE DATA',
    refresh_rate: '15s refresh',
    refresh_label: 'Refresh',
    theme_toggle_to_dark: 'Switch to Dark Mode',
    theme_toggle_to_light: 'Switch to Light Mode',
    lang_toggle: 'العربية',

    error_title: 'Backend connection issue',
    error_desc: 'Ensure the FastAPI backend service is running and reachable.',
    retry: 'Retry',

    currently_monitoring: 'CURRENTLY MONITORING',
    species_unconfirmed: 'Species not confirmed',
    growth_stage_unset: 'Growth stage not set',
    auto_mode_exec: 'AUTO MODE · EXECUTION ENABLED',
    auto_mode_locked: 'AUTO MODE · PUMP LOCKED',
    manual_control: 'MANUAL CONTROL',
    last_sensor_update: 'Last sensor update',
    no_telemetry_received: 'No telemetry received',
    water_now: 'Water now',
    switch_to_manual: 'Switch to Manual',
    switch_to_auto: 'Switch to Auto',
    run_check: 'Run check',
    watering_duration: 'Manual watering duration',
    safety_limit: 'Firmware safety limit: 15s',
    root_moisture: 'ROOT MOISTURE',
    vpd_index: 'VPD INDEX',

    sensor_network: 'SENSOR NETWORK',
    env_conditions: 'Environmental conditions',
    receiving_telemetry: 'Receiving telemetry',
    waiting_telemetry: 'Waiting for telemetry',

    metric_surface: 'Surface moisture',
    metric_mid: 'Mid-depth moisture',
    metric_root: 'Root-zone moisture',
    metric_temp: 'Air temperature',
    metric_humidity: 'Air humidity',
    metric_leaf_wetness: 'Leaf wetness',
    fresh_reading: 'Fresh sensor reading',
    no_fresh_reading: 'No fresh reading',
    primary_signal: 'Primary irrigation signal',
    missing_stale: 'Missing or stale reading',
    dht22_label: 'DHT22',
    optional_sensor: 'Optional sensor connected',
    not_implemented: 'Not implemented in current firmware',

    last_readings: 'LAST READINGS',
    soil_trends: 'Soil moisture trends',
    sensor_history_tag: 'SENSOR HISTORY',
    surface_legend: 'Surface',
    mid_legend: 'Mid-depth',
    root_legend: 'Root zone',
    waiting_first_readings: 'Waiting for your first readings',
    mqtt_hint: 'Once the ESP32 starts publishing telemetry, trends will appear here.',
    timestamp_note: 'Readings are timestamped by the backend on arrival.',
    records_loaded: 'records loaded',

    plant_climate: 'PLANT CLIMATE',
    stress_indicators: 'Stress indicators',
    vpd_band: 'VPD band',
    vpd_desc: 'Vapor pressure deficit estimates how strongly the air can draw moisture from the plant. It is a supporting signal, not a watering command by itself.',
    forecast_available: 'Forecast available',
    rain_probability: 'rain probability',
    weather_not_configured: 'Weather not configured',
    next_forecast_rain: 'Next forecast rain',
    weather_env_hint: 'Add OpenWeather settings to backend/.env',

    gemini_vision: 'GEMINI VISION',
    latest_photo: 'Latest plant photo',
    no_photo_yet: 'No photo received yet',
    cam_interval: 'ESP32-CAM uploads every ~30 minutes',
    captured_prefix: 'Captured',
    waiting_cam: 'Waiting for camera image',
    status_analyzed: 'ANALYZED',
    status_stored: 'IMAGE STORED',
    status_awaiting: 'AWAITING IMAGE',
    analyze_photo_btn: 'Analyze latest photo',
    observed_label: 'Observed',
    possible_stress_label: 'Possible stress signs',
    vision_disclaimer: 'Visual AI is suggestive only, not a confirmed disease diagnosis.',

    decision_engine: 'DECISION ENGINE',
    recent_decisions: 'Recent system decisions',
    no_decisions: 'No decisions logged yet. Use Run check to evaluate current data safely.',

    plant_knowledge: 'PLANT KNOWLEDGE',
    ask_plant: 'Ask about your plant',
    data_grounded: 'DATA GROUNDED',
    assistant_intro: 'Gemini analyzes the saved species profile, live readings, sensor history, VPD and recent decisions. Keep the species correct for plant-specific guidance.',
    chat_placeholder: 'e.g. Does my plant need water?',
    send_btn: 'Send question',
    assistant_name: 'Plant care assistant',
    prompt_root: 'What is the current root moisture?',
    prompt_analyze: 'Analyze my current plant condition using the latest readings, recent sensor trends, VPD, saved species profile, and recent watering events. Separate facts from uncertainty and suggest safe next steps without activating the pump.',
    prompt_summary: 'Summarize the latest plant conditions.',

    knowledge_base: 'KNOWLEDGE BASE',
    plant_profile: 'Plant profile',
    add_plant: 'Add plant',
    ideal_range: 'Configured moisture range',
    source_label: 'Species source',
    source_manual: 'User-confirmed',
    source_ai: 'AI suggestion',
    source_unconfirmed: 'Not confirmed',
    species_override_label: 'Plant type / species (you can set this manually)',
    species_placeholder: 'e.g. Tomato, Basil, Mint / طماطم',
    save_species: 'Save species',
    species_db_hint: 'Suggestions come from the local SQLite plant catalog. Manual selection takes priority over Gemini image guesses. Profile notes are references, not validated irrigation thresholds.',

    form_plant_id: 'Plant ID',
    form_name: 'Display name',
    form_species: 'Species',
    form_stage: 'Growth stage',
    form_min_moist: 'Min moisture %',
    form_max_moist: 'Max moisture %',
    form_save: 'Save plant profile',

    daily_notes: 'DAILY NOTES',
    plant_diary: 'Plant diary',
    generate_entry: 'Generate entry',
    diary_generated_from: 'Generated from stored sensor data',
    no_diary_yet: 'No diary entries yet. Generate one from available sensor observations.',

    footer_prototype: 'Greetopia · AI Plant Care Prototype',
    footer_freshness_warning: 'Verify sensor freshness before acting',

    download_eyebrow: 'GREETOPIA MOBILE',
    download_title: 'Your plants, in your pocket.',
    download_desc: 'Use the same plant profiles, sensor history, irrigation controls and Gemini assistant from your phone.',
    android_app: 'Android app',
    android_sub: 'Material-inspired Android design',
    ios_app: 'iPhone app',
    ios_sub: 'iOS glass-inspired design',
    install: 'Install',
    build_required: 'Build required',
    signing_required: 'Signing required',
    install_this_device: 'Install on this device',
    native_setup: 'Native release setup',
    install_this_desc: 'Install Greetopia as a home-screen app from this browser.',
    native_setup_desc: 'The native Android and iOS project source is included. A signed APK needs an Android build environment; an IPA must be built and signed with Apple Xcode and a valid Apple developer provisioning setup.',
    iphone_add_to_home: 'For iPhone browser install, use Share → Add to Home Screen when the website is deployed over HTTPS.',
    native_docs_link: 'Native app build documentation',
    close: 'Close',

    syncing_data: 'Syncing local data',
    mode_changed: 'Mode changed to',
    water_queued: 'Water command queued for',
    water_not_sent: 'Not sent',
    device_online: 'Device online',
    device_stale: 'Device stale (no recent data)',
    device_offline: 'Device offline',
    read_only_notice: 'Your account is read-only. Ask an administrator for operator access to control the pump.',
    last_command: 'Last command',
    use_as_species: 'Use as confirmed species',
    species_candidate_note: 'AI species suggestion (a candidate, not confirmed)',
    cmd_published_waiting: 'Sent to the broker; waiting for the device to confirm',
    decision_prefix: 'Decision',
    species_saved_prefix: 'Plant species saved as',
    species_cleared: 'Species cleared.',
    photo_analyzed_prefix: 'Photo analyzed by Gemini. Suggested species:',
    diary_generated: 'Daily sensor diary generated.',
    plant_profile_created: 'Plant profile created.',
  },
  ar: {
    // Auth
    signin_heading: 'مرحباً بعودتك',
    signin_sub: 'سجّل دخولك للوصول إلى لوحة مراقبة نباتاتك',
    signup_heading: 'إنشاء حسابك',
    signup_sub: 'ابدأ بمراقبة نباتاتك بتقنية الذكاء الاصطناعي',
    name_label: 'الاسم الكامل',
    email_label: 'البريد الإلكتروني',
    password_label: 'كلمة المرور',
    btn_signin: 'تسجيل الدخول',
    btn_signup: 'إنشاء حساب',
    btn_google: 'المتابعة عبر Google',
    switch_to_signup: 'ليس لديك حساب؟ أنشئ حساباً',
    switch_to_signin: 'لديك حساب بالفعل؟ سجّل الدخول',
    signing_in: 'جارٍ تسجيل الدخول...',
    auth_error_generic: 'حدث خطأ ما، يرجى المحاولة مرة أخرى.',
    sign_out: 'تسجيل الخروج',
    welcome_back: 'مرحباً بعودتك',
    signed_in_as: 'مسجّل دخولك بـ',

    brand_name: 'جريتوبيا',
    brand_sub: 'ذكاء رعاية النباتات',
    workspace: 'مساحة العمل',
    nav_overview: 'نظرة عامة',
    nav_profiles: 'ملفات النباتات',
    nav_history: 'سجل الحساسات',
    nav_diary: 'يوميات النبات',
    system_status: 'حالة النظام',
    api_unavailable: 'الخادم غير متصل',
    local_dashboard: 'لوحة التحكم متصلة',
    version: 'GREETOPIA · v0.1',

    topbar_eyebrow: 'مساحتك الزراعية / نظرة عامة',
    topbar_h1: 'رعاية النباتات،',
    topbar_em: 'بتناغم تام.',
    download_app: 'تحميل التطبيق',
    live_data: 'بيانات حية',
    refresh_rate: 'تحديث كل 15 ثانية',
    refresh_label: 'تحديث',
    theme_toggle_to_dark: 'التحويل للوضع الداكن',
    theme_toggle_to_light: 'التحويل للوضع الفاتح',
    lang_toggle: 'English',

    error_title: 'مشكلة في الاتصال بالخادم',
    error_desc: 'تأكد من تشغيل خادم FastAPI وإمكانية الوصول إليه.',
    retry: 'إعادة المحاولة',

    currently_monitoring: 'قيد المراقبة الآن',
    species_unconfirmed: 'لم يتم تأكيد الصنف',
    growth_stage_unset: 'مرحلة النمو غير محددة',
    auto_mode_exec: 'الوضع التلقائي · تشغيل المضخة مفعّل',
    auto_mode_locked: 'الوضع التلقائي · المضخة مقفلة للأمان',
    manual_control: 'تحكم يدوي',
    last_sensor_update: 'آخر تحديث للحساسات',
    no_telemetry_received: 'لم تصل قراءات بعد',
    water_now: 'اسقِ الآن',
    switch_to_manual: 'التحويل إلى يدوي',
    switch_to_auto: 'التحويل إلى تلقائي',
    run_check: 'فحص ذكي',
    watering_duration: 'مدة الري اليدوي',
    safety_limit: 'حد الأمان البرمجي: 15 ثانية',
    root_moisture: 'رطوبة الجذور',
    vpd_index: 'مؤشر عجز الضغط',

    sensor_network: 'شبكة الحساسات',
    env_conditions: 'الظروف البيئية المحيطة',
    receiving_telemetry: 'يتم استقبال القراءات الحية',
    waiting_telemetry: 'بانتظار قراءات الحساسات',

    metric_surface: 'رطوبة السطح',
    metric_mid: 'رطوبة العمق المتوسط',
    metric_root: 'رطوبة منطقة الجذور',
    metric_temp: 'درجة حرارة الجو',
    metric_humidity: 'نسبة رطوبة الجو',
    metric_leaf_wetness: 'بلل الأوراق',
    fresh_reading: 'قراءة حساس حديثة',
    no_fresh_reading: 'لا توجد قراءة حديثة',
    primary_signal: 'مؤشر الري الأساسي',
    missing_stale: 'قراءة مفقودة أو قديمة',
    dht22_label: 'حساس DHT22',
    optional_sensor: 'حساس اختياري متصل',
    not_implemented: 'غير مفعل بالبرنامج الحالي',

    last_readings: 'أحدث القراءات',
    soil_trends: 'اتجاهات رطوبة التربة',
    sensor_history_tag: 'سجل الحساسات',
    surface_legend: 'السطح',
    mid_legend: 'العمق المتوسط',
    root_legend: 'منطقة الجذور',
    waiting_first_readings: 'بانتظار وصول القراءات الأولى',
    mqtt_hint: 'بمجرد أن يبدأ جهاز ESP32 بإرسال القراءات، ستظهر الرسوم البيانية هنا.',
    timestamp_note: 'يتم تسجيل التوقيت الزمني للقراءات فور وصولها إلى الخادم.',
    records_loaded: 'سجل متوفر',

    plant_climate: 'مناخ النبات',
    stress_indicators: 'مؤشرات الإجهاد البيئي',
    vpd_band: 'نطاق VPD',
    vpd_desc: 'يقيس عجز ضغط البخار (VPD) شدة قدرة الهواء على سحب الرطوبة من النبات. وهو مؤشر استرشادي داعم وليس أمراً مباشراً بالري.',
    forecast_available: 'توقعات الطقس متوفرة',
    rain_probability: 'احتمال هطول الأمطار',
    weather_not_configured: 'الطقس غير مهيأ',
    next_forecast_rain: 'الأمطار المتوقعة القادمة',
    weather_env_hint: 'أضف مفاتيح OpenWeather في backend/.env',

    gemini_vision: 'رؤية جيميناي (GEMINI)',
    latest_photo: 'أحدث صورة للنبات',
    no_photo_yet: 'لم يتم استلام أي صورة بعد',
    cam_interval: 'تلتقط كاميرا ESP32-CAM وترسل كل ~30 دقيقة',
    captured_prefix: 'تم الالتقاط في',
    waiting_cam: 'بانتظار التقاط الكاميرا',
    status_analyzed: 'تم التحليل',
    status_stored: 'الصورة محفوظة',
    status_awaiting: 'بانتظار الصورة',
    analyze_photo_btn: 'تحليل أحدث صورة',
    observed_label: 'الملاحظات البصرية:',
    possible_stress_label: 'علامات إجهاد محتملة:',
    vision_disclaimer: 'تحليل الذكاء الاصطناعي البصري استرشادي فقط، ولا يعد تشخيصاً زراعياً قاطعاً.',

    decision_engine: 'محرك اتخاذ القرار',
    recent_decisions: 'أحدث قرارات النظام',
    no_decisions: 'لم تسجل قرارات بعد. استخدم "فحص ذكي" لتقييم البيانات الحالية بأمان.',

    plant_knowledge: 'المساعد الزراعي الذكي',
    ask_plant: 'اسأل عن نباتك',
    data_grounded: 'مدعوم بالبيانات الحية',
    assistant_intro: 'يقوم نموذج Gemini بتحليل الصنف والقراءات الحية وسجل الحساسات ومؤشر VPD والقرارات السابقة لتقديم مشورة دقيقة.',
    chat_placeholder: 'مثال: هل يحتاج نباتي إلى الري الآن؟',
    send_btn: 'إرسال السؤال',
    assistant_name: 'المساعد الزراعي الذكي',
    prompt_root: 'ما هي نسبة رطوبة الجذور حالياً؟',
    prompt_analyze: 'حلل حالة النبات الحالية باستخدام أحدث القراءات، وسجل الحساسات، ومؤشر VPD، وصنف النبات المحفوظ، وسجل الري الأخير. افصل بين الحقائق والشكوك واقترح خطوات آمنة تالية.',
    prompt_summary: 'لخص الظروف الحالية للنبات.',

    knowledge_base: 'قاعدة المعرفة',
    plant_profile: 'ملف النبات',
    add_plant: 'إضافة نبات',
    ideal_range: 'نطاق الرطوبة الموصى به',
    source_label: 'مصدر الصنف',
    source_manual: 'مؤكد يدوياً',
    source_ai: 'اقتراح ذكاء اصطناعي',
    source_unconfirmed: 'غير مؤكد',
    species_override_label: 'نوع / صنف النبات (يمكنك تحديده يدوياً)',
    species_placeholder: 'مثال: طماطم، ريحان، نعناع / Tomato',
    save_species: 'حفظ الصنف',
    species_db_hint: 'تأتي الاقتراحات من قاعدة بيانات النباتات المدمجة. الاختيار اليدوي يتفوق على تخمينات الكاميرا.',

    form_plant_id: 'معرف النبات (ID)',
    form_name: 'اسم العرض',
    form_species: 'الصنف / الفصيلة',
    form_stage: 'مرحلة النمو',
    form_min_moist: 'أدنى رطوبة %',
    form_max_moist: 'أقصى رطوبة %',
    form_save: 'حفظ ملف النبات',

    daily_notes: 'الملاحظات اليومية',
    plant_diary: 'يوميات النبات',
    generate_entry: 'توليد ملخص يومي',
    diary_generated_from: 'تم التوليد تلقائياً من بيانات الحساسات المخزنة',
    no_diary_yet: 'لا توجد تدوينات بعد. أنشئ ملخصاً من القراءات المسجلة.',

    footer_prototype: 'جريتوبيا · نموذج أولي ذكي لرعاية النباتات',
    footer_freshness_warning: 'تأكد من حداثة قراءات الحساسات قبل اتخاذ أي إجراء',

    download_eyebrow: 'تطبيق جريتوبيا للهاتف',
    download_title: 'نباتاتك في جيبك، أينما كنت.',
    download_desc: 'استخدم نفس ملفات النباتات، وسجل الحساسات، والتحكم بالري، ومساعد Gemini مباشرة من هاتفك.',
    android_app: 'تطبيق أندرويد',
    android_sub: 'تصميم ماتيريال مخصص للأندرويد',
    ios_app: 'تطبيق آيفون',
    ios_sub: 'تصميم زجاجي انسيابي لـ iOS',
    install: 'تثبيت',
    build_required: 'يتطلب بناء',
    signing_required: 'يتطلب توقيع',
    install_this_device: 'تثبيت على هذا الجهاز',
    native_setup: 'إعداد الإصدار الأصلي',
    install_this_desc: 'تثبيت جريتوبيا كتطبيق شاشة رئيسية (PWA) مباشرة من هذا المتصفح.',
    native_setup_desc: 'الملفات المصدرية الكاملة لنظامي Android و iOS متضمنة في المشروع. يحتاج ملف APK بيئة بناء أندرويد، بينما يحتاج IPA برنامج Xcode وتوقيع مطور أبل.',
    iphone_add_to_home: 'لتثبيت التطبيق على الآيفون من المتصفح: اضغط مشاركة ثم "إضافة إلى الشاشة الرئيسية".',
    native_docs_link: 'دليل بناء التطبيقات الأصلية',
    close: 'إغلاق',

    syncing_data: 'مزامنة البيانات المحلية...',
    mode_changed: 'تم تغيير الوضع إلى',
    water_queued: 'تم جدولة أمر الري لمدة',
    water_not_sent: 'لم يتم الإرسال',
    device_online: 'الجهاز متصل',
    device_stale: 'الجهاز متأخر (لا بيانات حديثة)',
    device_offline: 'الجهاز غير متصل',
    read_only_notice: 'حسابك للقراءة فقط. اطلب من المسؤول صلاحية المشغّل للتحكم في الطلمبة.',
    last_command: 'آخر أمر',
    use_as_species: 'اعتماد كنوع مؤكد',
    species_candidate_note: 'اقتراح الذكاء الاصطناعي للنوع (مرشح وليس مؤكدًا)',
    cmd_published_waiting: 'تم الإرسال إلى الـ broker وبانتظار تأكيد الجهاز',
    decision_prefix: 'القرار',
    species_saved_prefix: 'تم حفظ صنف النبات كـ',
    species_cleared: 'تم مسح الصنف.',
    photo_analyzed_prefix: 'تم تحليل الصورة بواسطة Gemini. الصنف المقترح:',
    diary_generated: 'تم توليد تدوينة الحساسات اليومية بنجاح.',
    plant_profile_created: 'تم إنشاء ملف النبات بنجاح.',
  },
};
