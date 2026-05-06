import styles from "./NumberInput.module.css"

export default function NumberInput(props) {
  let slider
  let number

  function onInput(evt) {
    slider.valueAsNumber = evt.target.valueAsNumber
    number.valueAsNumber = evt.target.valueAsNumber
    console.log(evt.target.valueAsNumber)
    props.onChange?.(evt.target.valueAsNumber)
  }

  return (
    <div class={styles.div}>
      <input
        ref={slider}
        type="range"
        name={props.name}
        value={props.value()}
        onInput={onInput}
        min={props.min}
        max={props.max}
        step={props.step}
      />
      <input
        ref={number}
        onInput={onInput}
        value={props.value()}
        type="number"
        min={props.min}
        max={props.max}
        step={props.step}
      />
    </div>
  )
}
